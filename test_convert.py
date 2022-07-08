import convert
import io


def test_simple():
    config = '''
    auto eth0
    iface eth0 inet static
        address 192.168.0.100
        netmask 255.255.255.0
        gateway 192.168.0.1
    '''

    f = io.StringIO(config)

    result = convert.convert_file(f, convert.AutoVivification())
    network = result['eth0.network']
    assert network['Match']['Name'] == 'eth0'
    assert network['Network']['Address'] == '192.168.0.100/24'
    assert network['Network']['Gateway'] == '192.168.0.1'
