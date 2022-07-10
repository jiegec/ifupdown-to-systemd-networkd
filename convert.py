import argparse
import configparser
import ipaddress
import os
import subprocess
import typing
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


def handle_iface(name: str, is_ipv4: bool, dhcp: str, config: typing.DefaultDict[str, typing.List[str]], result: AutoVivification):
    network = '{}.network'.format(name)
    netdev = '{}.netdev'.format(name)
    # Match Block
    result[network]['Match']['Name'] = name

    # Configs
    if 'address' in config and 'netmask' in config:
        # address and netmask
        netmask = ipaddress.IPv4Network(
            '0.0.0.0/{}'.format(config['netmask'][0]))
        result[network]['Network']['Address'] = '{}/{}'.format(
            config['address'][0], netmask.prefixlen)
    elif 'address' in config:
        # only address
        result[network]['Network']['Address'] = config['address'][0]

    if 'gateway' in config:
        result[network]['Network']['Gateway'] = config['gateway'][0]
    if 'hwaddress' in config:
        value = config['hwaddress'][0]
        parts = value.split(' ')
        # hwaddress ether
        if parts[0] == 'ether':
            result[network]['Link']['MACAddress'] = parts[1]
    if 'mtu' in config:
        result[network]['Link']['MTUBytes'] = config['mtu'][0]

    # VLAN:
    if '.' in name:
        index = name.rfind('.')
        device = name[:index]
        vlan_id = int(name[index+1:])

        result[netdev]['NetDev']['Name'] = name
        result[netdev]['NetDev']['Kind'] = 'vlan'
        result[netdev]['VLAN']['Id'] = vlan_id

        raw_network = '{}.network'.format(device)

        # Ensure Match is set
        result[raw_network]['Match']['Name'] = device

        # append to list of vlan interfaces
        vlan = result[raw_network]['Network']['VLAN']
        if type(vlan) is AutoVivification:
            vlan = [name]
        else:
            vlan.append(name)
        result[raw_network]['Network']['VLAN'] = vlan

    # Bonding
    if 'bond-slaves' in config:
        result[netdev]['NetDev']['Name'] = name
        result[netdev]['NetDev']['Kind'] = 'bond'

        # add slaves
        for intf in config['bond-slaves'][0].split(' '):
            result['{}.network'.format(intf)]['Network']['Bond'] = name
    if 'bond-xmit-hash-policy' in config:
        result[netdev]['Bond']['TransmitHashPolicy'] = config['bond-xmit-hash-policy'][0]
    if 'bond-mode' in config:
        result[netdev]['Bond']['Mode'] = config['bond-mode'][0]
    if 'bond-miimon' in config:
        result[netdev]['Bond']['MIIMonitorSec'] = float(
            config['bond-miimon'][0]) / 1000
    if 'bond-lacp-rate' in config:
        result[netdev]['Bond']['LACPTransmitRate'] = config['bond-lacp-rate'][0]
    if 'ad_actor_sys_prio' in config:
        result[netdev]['Bond']['AdActorSystemPriority'] = config['ad_actor_sys_prio'][0]
    if 'ad_select' in config:
        result[netdev]['Bond']['BondAdSelect'] = config['ad_select'][0]

    # Custom routes
    if 'post-up' in config:
        for command in config['post-up']:
            parts = command.split(' ')

            if parts[0] == 'ip' and parts[1] == 'route' and parts[2] == 'add':
                # ip route add
                route = {}
                destination = parts[3]
                if destination == 'default':
                    destination = '0.0.0.0/0'

                route['Destination'] = destination

                i = 4
                while i < len(parts):
                    if parts[i] == 'via':
                        gateway = parts[i+1]
                        route['Gateway'] = gateway
                        i += 2
                    elif parts[i] == 'table':
                        table = parts[i+1]
                        route['Table'] = table
                        i += 2
                    else:
                        i += 1

                # append to list of routes
                routes = result[network]['Route']
                if type(routes) is AutoVivification:
                    routes = [route]
                else:
                    routes.append(route)
                result[network]['Route'] = routes
            elif parts[0] == 'ip' and parts[1] == 'rule' and parts[2] == 'add':
                # ip rule add
                rule = {}
                i = 3
                while i < len(parts):
                    if parts[i] == 'from':
                        rule_from = parts[i+1]
                        rule['From'] = rule_from
                        i += 2
                    elif parts[i] == 'table':
                        table = parts[i+1]
                        rule['Table'] = table
                        i += 2
                    else:
                        i += 1

                # append to list of rules
                rules = result[network]['RoutingPolicyRule']
                if type(rules) is AutoVivification:
                    rules = [rule]
                else:
                    rules.append(rule)
                result[network]['RoutingPolicyRule'] = rules

    # DHCP
    if dhcp == 'dhcp':
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


def convert_file(f: typing.IO, result: AutoVivification):
    current_iface = None
    current_ipv4 = True
    current_type = 'static'
    current_configs = defaultdict(list)
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
                current_configs = defaultdict(list)

            current_iface = parts[1]
            current_ipv4 = parts[2] == 'inet'
            current_type = parts[3]
        elif current_iface is not None:
            key = parts[0]
            value = ' '.join(parts[1:])
            current_configs[key].append(value)
    if current_iface is not None:
        result = handle_iface(
            current_iface, current_ipv4, current_type, current_configs, result)
        current_configs = defaultdict(list)
    return result


def convert(interfaces: str, output: str):
    print("Converting {} to systemd-networkd configs in {}".format(
        interfaces, output))
    # filename -> dict
    result = AutoVivification()
    with open(interfaces, 'r') as f:
        result = convert_file(f, result)
    for file in result:
        # configparse do not support repeated keys
        # let's do it ourselves
        data = ''
        for section in result[file]:
            content = result[file][section]
            if type(content) is list:
                # multiple sections with same key
                for inner in content:
                    data += '[{}]\n'.format(section)

                    for key in inner:
                        value = inner[key]
                        if type(value) is list:
                            # repeat each value
                            for val in value:
                                data += '{} = {}\n'.format(key, val)
                        else:
                            data += '{} = {}\n'.format(key, value)
                    data += '\n'
            else:
                # single section
                data += '[{}]\n'.format(section)

                for key in content:
                    value = content[key]
                    if type(value) is list:
                        # repeat each value
                        for val in value:
                            data += '{} = {}\n'.format(key, val)
                    else:
                        data += '{} = {}\n'.format(key, value)
                data += '\n'

        dest = os.path.join(output, file)

        if os.path.exists(dest):
            print('Diffing {}'.format(dest))
            proc = subprocess.Popen(
                args=['diff', '-u', dest, '-'], executable='diff', stdin=subprocess.PIPE)
            if proc.stdin is not None:
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
