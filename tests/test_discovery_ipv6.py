from network.discovery import _parse_ip_neigh_output


def test_parse_ipv6_neighbor_table_entry() -> None:
    hosts = _parse_ip_neigh_output(
        "fe80::1234 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
    )
    assert len(hosts) == 1
    assert hosts[0].ip == "fe80::1234"
    assert hosts[0].interface == "wlan0"
    assert hosts[0].mac == "aa:bb:cc:dd:ee:ff"
    assert hosts[0].state == "REACHABLE"


def test_parse_ipv4_and_ipv6_neighbor_tables_together() -> None:
    hosts = _parse_ip_neigh_output(
        "192.168.1.20 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
        "fe80::1234 dev wlan0 lladdr aa:bb:cc:dd:ee:ff STALE\n"
    )
    assert {host.ip for host in hosts} == {"192.168.1.20", "fe80::1234"}
