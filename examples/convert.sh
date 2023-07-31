#!/bin/sh
set -e
for folder in bonding post-up simple static static-v6 vlan dhcp; do
    yes | poetry run ifupdown-to-systemd-networkd --interfaces $folder/interfaces --output $folder --tables $folder/rt_tables --config $folder/tables.conf --systemd-version 248
done
