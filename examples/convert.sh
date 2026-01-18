#!/bin/sh
set -e
for folder in bonding post-up simple static static-v6 vlan dhcp dhcp6 dhcp46 issue1; do
    yes | poetry run ifupdown-to-systemd-networkd --interfaces $folder/interfaces --output $folder --tables $folder/rt_tables --config $folder/tables.conf --systemd-version 248
done
