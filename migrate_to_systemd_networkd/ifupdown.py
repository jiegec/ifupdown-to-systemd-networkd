import argparse
import ipaddress
import os
import typing
from collections import defaultdict

from migrate_to_systemd_networkd.utils import (
    AutoVivification,
    ask_write_file,
    probe_systemd,
)


class Converter:
    interfaces: str
    tables: str
    output: str
    config: str

    use_table_name: bool
    table_mapping: typing.Dict[str, int]
    systemd_version: int

    def __init__(
        self,
        interfaces: str,
        tables: str,
        output: str,
        config: str,
        systemd_version: str,
    ) -> None:
        self.interfaces = interfaces
        self.tables = tables
        self.output = output
        self.config = config
        self.use_table_name = True
        self.systemd_version = systemd_version

    def work(self):
        if self.systemd_version is None:
            self.systemd_version = probe_systemd()
        self.table_mapping = self.get_routes()

        # https://github.com/systemd/systemd/commit/c038ce4606f93d9e58147f87703125270fb744e2
        if int(self.systemd_version) >= 248:
            self.convert_routes()
            self.use_table_name = True
        else:
            self.use_table_name = False
        self.convert()

    def handle_iface(
        self,
        name: str,
        is_ipv4: bool,
        method: str,
        config: typing.DefaultDict[str, typing.List[str]],
        result: AutoVivification,
    ):
        network = "{}.network".format(name)
        netdev = "{}.netdev".format(name)
        # Match Block
        result[network]["Match"]["Name"] = name

        # Configs
        if "address" in config:
            address_config = AutoVivification()
            if "netmask" in config:
                # address and netmask
                netmask = ipaddress.IPv4Network(
                    "0.0.0.0/{}".format(config["netmask"][0]))
                address = "{}/{}".format(
                    config["address"][0], netmask.prefixlen
                )
            else:
                # only address
                address = config["address"][0]
            address_config["Address"] = address

            if method == "static":
                if "scope" in config:
                    address_config["Scope"] = config["scope"][0]
                if "pointopoint" in config:
                    address_config["Peer"] = config["pointopoint"][0]
                if "metric" in config:
                    address_config["RouteMetric"] = config["metric"][0]

            if "Address" in result[network]:
                result[network]["Address"].append(address_config)
            else:
                result[network]["Address"] = [address_config]

        if method == "static" and not is_ipv4:
            # inet6 static
            result[network]["Network"]["IPv6AcceptRA"] = "no"

        if "gateway" in config:
            gateway = config["gateway"][0]
            if "Gateway" in result[network]["Network"]:
                result[network]["Network"]["Gateway"].append(gateway)
            else:
                result[network]["Network"]["Gateway"] = [gateway]

        if "hwaddress" in config:
            value = config["hwaddress"][0]
            parts = value.split(" ")
            # hwaddress ether
            if parts[0] == "ether":
                result[network]["Link"]["MACAddress"] = parts[1]
        if "mtu" in config:
            result[network]["Link"]["MTUBytes"] = config["mtu"][0]

        # VLAN:
        if "." in name:
            index = name.rfind(".")
            device = name[:index]
            vlan_id = int(name[index + 1:])

            result[netdev]["NetDev"]["Name"] = name
            result[netdev]["NetDev"]["Kind"] = "vlan"
            result[netdev]["VLAN"]["Id"] = vlan_id

            raw_network = "{}.network".format(device)

            # Ensure Match is set
            result[raw_network]["Match"]["Name"] = device

            # append to list of vlan interfaces
            vlan = result[raw_network]["Network"]["VLAN"]
            if type(vlan) is AutoVivification:
                vlan = [name]
            elif name not in vlan:
                vlan.append(name)
            result[raw_network]["Network"]["VLAN"] = vlan

        # Bonding
        if "bond-slaves" in config:
            result[netdev]["NetDev"]["Name"] = name
            result[netdev]["NetDev"]["Kind"] = "bond"

            # add slaves
            for intf in config["bond-slaves"][0].split(" "):
                result["{}.network".format(intf)]["Network"]["Bond"] = name
                # Add match if the interfaces is not declared elsewhere
                result["{}.network".format(intf)]["Match"]["Name"] = intf
        if "bond-xmit-hash-policy" in config:
            result[netdev]["Bond"]["TransmitHashPolicy"] = config[
                "bond-xmit-hash-policy"
            ][0]
        if "bond-mode" in config:
            policy = [
                "balance-rr",
                "active-backup",
                "balance-xor",
                "broadcast",
                "802.3ad",
                "balance-tlb",
                "balance-alb",
            ]
            result[netdev]["Bond"]["Mode"] = policy[int(
                config["bond-mode"][0])]
        if "bond-miimon" in config:
            result[netdev]["Bond"]["MIIMonitorSec"] = (
                float(config["bond-miimon"][0]) / 1000
            )
        if "bond-lacp-rate" in config:
            rate = {"30": "slow", "1": "fast"}
            result[netdev]["Bond"]["LACPTransmitRate"] = rate[
                config["bond-lacp-rate"][0]
            ]
        if "ad_actor_sys_prio" in config:
            result[netdev]["Bond"]["AdActorSystemPriority"] = config[
                "ad_actor_sys_prio"
            ][0]
        if "ad_select" in config:
            result[netdev]["Bond"]["AdSelect"] = config["ad_select"][0]

        # Custom routes
        if "post-up" in config:
            for command in config["post-up"]:
                parts = command.split(" ")

                if parts[0] == "ip" and parts[1] == "route" and parts[2] == "add":
                    # ip route add
                    route = {}
                    destination = parts[3]
                    if destination == "default":
                        destination = "0.0.0.0/0"

                    route["Destination"] = destination

                    i = 4
                    while i < len(parts):
                        if parts[i] == "via":
                            gateway = parts[i + 1]
                            route["Gateway"] = gateway
                            i += 2
                        elif parts[i] == "table":
                            table = parts[i + 1]
                            if self.use_table_name:
                                route["Table"] = table
                            else:
                                route["Table"] = self.table_mapping[table]
                            i += 2
                        else:
                            i += 1

                    # append to list of routes
                    routes = result[network]["Route"]
                    if type(routes) is AutoVivification:
                        routes = [route]
                    else:
                        routes.append(route)
                    result[network]["Route"] = routes
                elif parts[0] == "ip" and parts[1] == "rule" and parts[2] == "add":
                    # ip rule add
                    rule = {}
                    i = 3
                    while i < len(parts):
                        if parts[i] == "from":
                            rule_from = parts[i + 1]
                            rule["From"] = rule_from
                            i += 2
                        elif parts[i] == "table":
                            table = parts[i + 1]
                            if self.use_table_name:
                                rule["Table"] = table
                            else:
                                rule["Table"] = self.table_mapping[table]
                            i += 2
                        else:
                            i += 1

                    # append to list of rules
                    rules = result[network]["RoutingPolicyRule"]
                    if type(rules) is AutoVivification:
                        rules = [rule]
                    else:
                        rules.append(rule)
                    result[network]["RoutingPolicyRule"] = rules

        # DHCP
        if method == "dhcp":
            if "DHCP" in result[network]["Network"]:
                current = result[network]["Network"]["DHCP"]
            else:
                current = "no"

            if is_ipv4:
                if current == "no":
                    current = "ipv4"
                elif current == "ipv6":
                    current = "yes"
            else:
                if current == "no":
                    current = "ipv6"
                elif current == "ipv4":
                    current = "yes"
            result[network]["Network"]["DHCP"] = current

            if is_ipv4:
                if "hostname" in config:
                    result[network]["DHCPv4"]["Hostname"] = config["hostname"][0]
                if "metric" in config:
                    result[network]["DHCPv4"]["RouteMetric"] = config["metric"][0]
                if "vendor" in config:
                    result[network]["DHCPv4"]["VendorClassIdentifier"] = config[
                        "vendor"
                    ][0]
                if "client" in config:
                    result[network]["DHCPv4"]["UserClass"] = config["client"][0]
        return result

    def convert_file(self, f: typing.IO, result: AutoVivification):
        current_iface = None
        current_ipv4 = True
        current_method = "static"
        current_configs = defaultdict(list)
        for line in f:
            line = line.strip()
            parts = line.split(" ")

            # comments
            if line.startswith("#"):
                continue
            elif line.startswith("iface"):
                if current_iface is not None:
                    result = self.handle_iface(
                        current_iface,
                        current_ipv4,
                        current_method,
                        current_configs,
                        result,
                    )
                    current_configs = defaultdict(list)

                current_iface = parts[1]
                current_ipv4 = parts[2] == "inet"
                current_method = parts[3]
            elif current_iface is not None:
                key = parts[0]
                value = " ".join(parts[1:])
                current_configs[key].append(value)
        if current_iface is not None:
            result = self.handle_iface(
                current_iface, current_ipv4, current_method, current_configs, result
            )
            current_configs = defaultdict(list)
        return result

    def convert(self):
        print(
            "Converting {} to systemd-networkd configs in {}".format(
                self.interfaces, self.output
            )
        )
        # filename -> dict
        result = AutoVivification()
        with open(self.interfaces, "r") as f:
            result = self.convert_file(f, result)
        for file in result:
            # configparse do not support repeated keys
            # let's do it ourselves
            data = ""
            data += "# Generated from /etc/network/interfaces\n"
            data += "# Using jiegec/ifupdown-to-systemd-networkd\n"
            for section in result[file]:
                content = result[file][section]
                if type(content) is list:
                    # multiple sections with same key
                    for inner in content:
                        data += "[{}]\n".format(section)

                        for key in inner:
                            value = inner[key]
                            if type(value) is list:
                                # repeat each value
                                for val in value:
                                    data += "{} = {}\n".format(key, val)
                            else:
                                data += "{} = {}\n".format(key, value)
                        data += "\n"
                else:
                    # single section
                    data += "[{}]\n".format(section)

                    for key in content:
                        value = content[key]
                        if type(value) is list:
                            # repeat each value
                            for val in value:
                                data += "{} = {}\n".format(key, val)
                        else:
                            data += "{} = {}\n".format(key, value)
                    data += "\n"

            dest = os.path.join(self.output, file)

            ask_write_file(dest, data)

    def get_routes(self):
        """Collect custom table names from /etc/iproute2/rt_tables"""
        result = {}
        if not os.path.exists(self.tables):
            return result

        with open(self.tables, "r") as f:
            for line in f:
                line = line.strip()
                if len(line) == 0 or line[0] == "#":
                    continue

                parts = line.split("\t")
                if len(parts) == 2:
                    table_id = parts[0]
                    table_name = parts[1]
                    if table_name in ("local", "main", "default", "unspec"):
                        continue
                    result[table_name] = table_id
        return result

    def convert_routes(self):
        if len(self.table_mapping) == 0:
            return
        data = "[Network]\n"
        data += "RouteTable="
        entries = []
        for name in self.table_mapping:
            entries.append("{}:{}".format(name, self.table_mapping[name]))
        data += " ".join(entries)
        data += "\n"
        ask_write_file(self.config, data)


def run():
    parser = argparse.ArgumentParser(
        description="Convert ifupdown configs to systemd-networkd"
    )
    parser.add_argument(
        "--interfaces",
        required=False,
        help="path to ifupdown config, default to /etc/network/interfaces",
        default="/etc/network/interfaces",
    )
    parser.add_argument(
        "--tables",
        required=False,
        help="path to iproute2 rt_tables, default to /etc/iproute2/rt_tables",
        default="/etc/iproute2/rt_tables",
    )
    parser.add_argument(
        "--output",
        required=False,
        help="output folder for systemd-networkd network config, default to /etc/systemd/network",
        default="/etc/systemd/network",
    )
    parser.add_argument(
        "--config",
        required=False,
        help="output config for systemd-networkd service config, default to /etc/systemd/networkd.conf.d/tables.conf",
        default="/etc/systemd/networkd.conf.d/tables.conf",
    )
    parser.add_argument("--systemd-version", required=False,
                        help="systemd version")
    args = parser.parse_args()

    converter = Converter(
        args.interfaces, args.tables, args.output, args.config, args.systemd_version
    )
    converter.work()


if __name__ == "__main__":
    run()
