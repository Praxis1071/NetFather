from network.presence import parse_neighbor_event


def test_parse_added_neighbor_event() -> None:
    event = parse_neighbor_event("192.168.1.25 dev wlan0 lladdr AA:BB:CC:DD:EE:FF REACHABLE")
    assert event is not None
    assert event.address == "192.168.1.25"
    assert event.mac == "aa:bb:cc:dd:ee:ff"
    assert event.kind == "changed"


def test_parse_deleted_neighbor_event() -> None:
    event = parse_neighbor_event("Deleted 192.168.1.25 dev wlan0 lladdr aa:bb:cc:dd:ee:ff")
    assert event is not None
    assert event.address == "192.168.1.25"
    assert event.kind == "removed"


def test_ignore_empty_neighbor_event() -> None:
    assert parse_neighbor_event("   ") is None
