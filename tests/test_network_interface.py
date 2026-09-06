from network.interface import NetworkStatus, _parse_route_get_output


def test_linux_route_output_parser() -> None:
    status = _parse_route_get_output("192.168.1.20 via 192.168.1.1 dev wlan0 src 192.168.1.10 uid 1000")
    assert status.interface == "wlan0"
    assert status.gateway == "192.168.1.1"
    assert status.local_ip == "192.168.1.10"


def test_network_status_defaults_are_unknown() -> None:
    status = NetworkStatus()
    assert status.interface is None
    assert status.local_ip is None
    assert status.gateway is None
