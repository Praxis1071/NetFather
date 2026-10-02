from network.deep_scan import _parse_nmap_xml, _validate_local_target, run_deep_scan


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


def test_deep_scan_inventory_is_limited_to_discovered_live_hosts(monkeypatch) -> None:
    calls = []
    discovery_xml = """<?xml version="1.0"?>
<nmaprun>
  <host><status state="up"/><address addr="192.168.1.21" addrtype="ipv4"/></host>
  <host><status state="down"/><address addr="192.168.1.22" addrtype="ipv4"/></host>
</nmaprun>
"""
    inventory_xml = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="192.168.1.21" addrtype="ipv4"/>
    <ports><port protocol="tcp" portid="22"><state state="open"/><service name="ssh"/></port></ports>
  </host>
</nmaprun>
"""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        output = discovery_xml if len(calls) == 1 else inventory_xml
        return type("Completed", (), {"returncode": 0, "stdout": output, "stderr": ""})()

    monkeypatch.setattr("network.deep_scan.nmap_available", lambda: True)
    monkeypatch.setattr("network.deep_scan.privileged", lambda: False)
    monkeypatch.setattr("network.deep_scan.subprocess.run", fake_run)

    report = run_deep_scan("192.168.1.0/24", include_udp=False, include_os=False)

    assert report.hosts[0].ip == "192.168.1.21"
    assert len(calls) == 2
    assert "-sn" in calls[0][0]
    assert "-Pn" in calls[1][0]
    assert calls[1][0][-2:] == ["-iL", "-"]
    assert calls[1][1]["input"] == "192.168.1.21\n"


def test_deep_scan_skips_expensive_inventory_when_no_hosts_are_up(monkeypatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Completed", (), {
            "returncode": 0,
            "stdout": """<?xml version="1.0"?><nmaprun>
              <host><status state="down"/><address addr="192.168.1.21" addrtype="ipv4"/></host>
            </nmaprun>""",
            "stderr": "",
        })()

    monkeypatch.setattr("network.deep_scan.nmap_available", lambda: True)
    monkeypatch.setattr("network.deep_scan.privileged", lambda: False)
    monkeypatch.setattr("network.deep_scan.subprocess.run", fake_run)

    report = run_deep_scan("192.168.1.0/24", include_udp=False, include_os=False)

    assert report.hosts == ()
    assert len(calls) == 1
    assert any("canlı cihaz bulamadı" in warning for warning in report.warnings)
