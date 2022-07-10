import convert
import io


def test_simple():
    config = '''
    auto eth0
    iface eth0 inet static
        address 192.168.0.100
        netmask 255.255.255.0
        gateway 192.168.0.1
        hwaddress ether 00:11:22:33:44:55
        mtu 1024
    '''

    f = io.StringIO(config)

    result = convert.convert_file(f, convert.AutoVivification())
    network = result['eth0.network']
    assert network['Match']['Name'] == 'eth0'
    assert network['Network']['Address'] == '192.168.0.100/24'
    assert network['Network']['Gateway'] == '192.168.0.1'
    assert network['Link']['MTUBytes'] == '1024'
    assert network['Link']['MACAddress'] == '00:11:22:33:44:55'


def test_bonding():
    config = '''
    auto bond0
    iface bond0 inet static
        bond-slaves eth1 eth2
    '''

    f = io.StringIO(config)

    result = convert.convert_file(f, convert.AutoVivification())
    netdev = result['bond0.netdev']
    assert netdev['NetDev']['Name'] == 'bond0'
    assert netdev['NetDev']['Kind'] == 'bond'

    network = result['eth1.network']
    assert network['Network']['Bond'] == 'bond0'

    network = result['eth2.network']
    assert network['Network']['Bond'] == 'bond0'


def test_vlan():
    config = '''
    auto eth0.123
    iface eth0.123 inet static
        address 192.168.0.1/24
    '''

    f = io.StringIO(config)

    result = convert.convert_file(f, convert.AutoVivification())
    network = result['eth0.network']
    assert network['Network']['VLAN'] == ['eth0.123']

    network = result['eth0.123.network']
    assert network['Network']['Address'] == '192.168.0.1/24'

    netdev = result['eth0.123.netdev']
    assert netdev['NetDev']['Name'] == 'eth0.123'
    assert netdev['NetDev']['Kind'] == 'vlan'
    assert netdev['VLAN']['Id'] == 123


def test_custom_routes():
    config = '''
    auto eth0
    iface eth0 inet static
        post-up ip route add default via 192.168.0.1
        post-up ip route add default via 192.168.1.1 table some_table
        post-up ip rule add from 192.168.0.2 table some_table
    '''

    f = io.StringIO(config)

    result = convert.convert_file(f, convert.AutoVivification())
    network = result['eth0.network']
    assert network['Match']['Name'] == 'eth0'

    assert network['Route'][0]['Destination'] == '0.0.0.0/0'
    assert network['Route'][0]['Gateway'] == '192.168.0.1'

    assert network['Route'][1]['Destination'] == '0.0.0.0/0'
    assert network['Route'][1]['Gateway'] == '192.168.1.1'
    assert network['Route'][1]['Table'] == 'some_table'

    assert network['RoutingPolicyRule'][0]['From'] == '192.168.0.2'
    assert network['RoutingPolicyRule'][0]['Table'] == 'some_table'
