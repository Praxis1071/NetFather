import pytest

from network.discovery import _parse_ip_neigh_output, observations_from_hosts


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


@pytest.mark.parametrize("state", ["STALE", "DELAY", "PROBE", "PERMANENT", "NOARP", "NONE", ""])
def test_cache_entries_remain_inventory_without_refreshing_presence(state):
    hosts = _parse_ip_neigh_output(
        f"fe80::1234 dev wlan0 lladdr aa:bb:cc:dd:ee:ff router {state}\n"
    )
    assert len(hosts) == 1
    assert not hosts[0].presence_confirmed
    assert observations_from_hosts(hosts) == []


@pytest.mark.parametrize("flags", ["router REACHABLE", "REACHABLE router", "reachable managed"])
def test_reachable_state_is_parsed_separately_from_flags(flags):
    hosts = _parse_ip_neigh_output(
        f"fe80::1234 dev wlan0 lladdr aa:bb:cc:dd:ee:ff {flags}\n"
    )
    assert hosts[0].state == "REACHABLE"
    assert len(observations_from_hosts(hosts)) == 1
