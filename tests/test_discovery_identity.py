from network.discovery import DiscoveredHost, observations_from_hosts


def test_observations_from_hosts_assigns_confidence_by_source() -> None:
    observations = observations_from_hosts([
        DiscoveredHost(
            ip="192.168.1.20",
            mac="aa-bb-cc-dd-ee-ff",
            hostname="phone",
            vendor="Example",
            interface="wlan0",
            source="active+passive",
        ),
        DiscoveredHost(
            ip="192.168.1.30",
            mac="00:11:22:33:44:55",
            interface="eth0",
            source="passive",
        ),
    ])

    assert len(observations) == 2
    assert observations[0].mac == "AA:BB:CC:DD:EE:FF"
    assert observations[0].confidence == 1.0
    assert observations[0].source == "active+passive"
    assert observations[1].confidence == 0.8


def test_hosts_without_mac_do_not_become_device_identities() -> None:
    observations = observations_from_hosts([
        DiscoveredHost(ip="192.168.1.50", source="passive"),
    ])

    assert observations == []
