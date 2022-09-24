#!/bin/sh
for folder in bonding post-up simple static vlan dhcp; do
    yes | poetry run ifupdown-to-systemd-networkd --interfaces $folder/interfaces --output $folder --tables $folder/rt_tables --config $folder/tables.conf --systemd-version 248
done
