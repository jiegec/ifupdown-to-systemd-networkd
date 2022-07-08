import argparse
import configparser
import ipaddress
import os
import subprocess
import click
import io
from collections import defaultdict

# https://stackoverflow.com/a/2600847/2148614


class AutoVivification(dict):
    """Implementation of perl's autovivification feature."""

    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            value = self[item] = type(self)()
            return value


def handle_iface(name, is_ipv4, type, config, result):
    network = '{}.network'.format(name)
    # Match Block
    result[network]['Match']['Name'] = name

    # Configs
    if 'address' in config and 'netmask' in config:
        netmask = ipaddress.IPv4Network('0.0.0.0/{}'.format(config['netmask']))
        result[network]['Network']['Address'] = '{}/{}'.format(
            config['address'], netmask.prefixlen)
    if 'gateway' in config:
        result[network]['Network']['Gateway'] = config['gateway']
    if 'hwaddress ether' in config:
        result[network]['Link']['MACAddress'] = config['hwaddress ether']

    if type == 'dhcp':
        if 'DHCP' in result[network]['Network']:
            current = result[network]['Network']['DHCP']
        else:
            current = 'no'

        if is_ipv4:
            if current == 'no':
                current = 'ipv4'
            elif current == 'ipv6':
                current = 'yes'
        else:
            if current == 'no':
                current = 'ipv6'
            elif current == 'ipv4':
                current = 'yes'
        result[network]['Network']['DHCP'] = current
    return result


def convert_file(f, result):
    current_iface = None
    current_ipv4 = True
    current_type = 'static'
    current_configs = {}
    for line in f:
        line = line.strip()
        parts = line.split(' ')

        # comments
        if line.startswith('#'):
            continue
        elif line.startswith('iface'):
            if current_iface is not None:
                result = handle_iface(
                    current_iface, current_ipv4, current_type, current_configs, result)
                current_configs = {}

            current_iface = parts[1]
            current_ipv4 = parts[2] == 'inet'
            current_type = parts[3]
        elif current_iface is not None:
            key = ' '.join(parts[:-1])
            value = parts[-1]
            current_configs[key] = value
    if current_iface is not None:
        result = handle_iface(
            current_iface, current_ipv4, current_type, current_configs, result)
        current_configs = {}
    return result


def convert(interfaces, output):
    print("Converting {} to systemd-networkd configs in {}".format(
        interfaces, output))
    # filename -> dict
    result = AutoVivification()
    with open(interfaces, 'r') as f:
        result = convert_file(f, result)
    for file in result:
        # https://stackoverflow.com/a/23836686/2148614
        config = configparser.ConfigParser()
        config.optionxform = str

        config.read_dict(result[file])
        with io.StringIO() as f:
            config.write(f)

            f.seek(0)
            data = f.read()

        dest = os.path.join(output, file)

        if os.path.exists(dest):
            print('Diffing {}'.format(dest))
            proc = subprocess.Popen(
                args=['diff', '-u', dest, '-'], executable='diff', stdin=subprocess.PIPE)
            proc.stdin.write(data.encode('utf-8'))
            proc.stdin.close()
            proc.wait()
        else:
            print('New configuration {}'.format(dest))
            print(data)

        if click.confirm('Write to {}'.format(dest)):
            with open(dest, 'w') as f:
                f.write(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Convert ifupdown configs to systemd-networkd")
    parser.add_argument('--interfaces', required=False,
                        help='path to ifupdown config, default to /etc/network/interfaces', default='/etc/network/interfaces')
    parser.add_argument('--output', required=False,
                        help='output folder for systemd-networkd config, default to /etc/systemd/network', default='/etc/systemd/network')
    args = parser.parse_args()

    convert(args.interfaces, args.output)
