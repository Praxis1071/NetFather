from network.deep_scan import _parse_nmap_xml, _validate_local_target


def test_deep_scan_rejects_non_local_targets() -> None:
    try:
        _validate_local_target("8.8.8.0/24")
    except ValueError as exc:
        assert "local" in str(exc).lower() or "private" in str(exc).lower()
    else:
        raise AssertionError("public target must be rejected")


def test_deep_scan_parses_services_and_ports() -> None:
    xml = '''<?xml version="1.0"?>
    <nmaprun>
      <host>
        <status state="up"/>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <address addr="aa:bb:cc:dd:ee:ff" addrtype="mac" vendor="Example Vendor"/>
        <hostnames><hostname name="router.local"/></hostnames>
        <ports>
          <port protocol="tcp" portid="22"><state state="open"/><service name="ssh" product="OpenSSH" version="9.9"/></port>
          <port protocol="udp" portid="53"><state state="open"/><service name="domain" product="BIND" version="9"/></port>
        </ports>
        <os><osmatch name="Linux 6.x" accuracy="96"><osclass type="general purpose"/></osmatch></os>
        <times srtt="12345"/>
      </host>
    </nmaprun>'''
    results = _parse_nmap_xml(xml)
    assert len(results) == 1
    result = results[0]
    assert result.ip == "192.168.1.10"
    assert result.mac == "aa:bb:cc:dd:ee:ff"
    assert result.hostname == "router.local"
    assert result.open_tcp_ports == (22,)
    assert result.open_udp_ports == (53,)
    assert "OpenSSH 9.9" in result.services[0]
    assert result.os_name == "Linux 6.x"
    assert result.os_accuracy == 96
