#!/bin/sh
for folder in bonding post-up simple static vlan; do
    yes | python3 ../convert.py --interfaces $folder/interfaces --output $folder --config $folder/tables.conf --systemd-version 248
done