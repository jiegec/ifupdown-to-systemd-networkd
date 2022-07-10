#!/bin/sh
yes | python3 ../convert.py --interfaces simple/interfaces --output simple
yes | python3 ../convert.py --interfaces vlan/interfaces --output vlan
yes | python3 ../convert.py --interfaces bonding/interfaces --output bonding
yes | python3 ../convert.py --interfaces post-up/interfaces --output post-up