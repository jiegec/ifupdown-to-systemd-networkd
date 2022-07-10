#!/bin/sh
for folder in bonding post-up simple static vlan dhcp; do
    yes | python3 ../convert.py --interfaces $folder/interfaces --output $folder --tables $folder/rt_tables --config $folder/tables.conf --systemd-version 248
done