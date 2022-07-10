# ifupdown-to-systemd-networkd

Convert `/etc/network/interfaces` to systemd networkd configs.

Supported:

1. Basic: address, gateway, mtu
2. Bonding
3. VLAN
4. Simple post-up scripts e.g. `ip route add` & `ip rule add`