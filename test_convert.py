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