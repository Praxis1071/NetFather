import pytest

from network.presence import parse_neighbor_event


def test_parse_added_neighbor_event() -> None:
    event = parse_neighbor_event("192.168.1.25 dev wlan0 lladdr AA:BB:CC:DD:EE:FF REACHABLE")
    assert event is not None
    assert event.address == "192.168.1.25"
    assert event.mac == "aa:bb:cc:dd:ee:ff"
    assert event.kind == "added"


def test_parse_deleted_neighbor_event() -> None:
    event = parse_neighbor_event("Deleted 192.168.1.25 dev wlan0 lladdr aa:bb:cc:dd:ee:ff")
    assert event is not None
    assert event.address == "192.168.1.25"
    assert event.kind == "removed"


def test_ignore_empty_neighbor_event() -> None:
    assert parse_neighbor_event("   ") is None


def test_parse_failed_neighbor_event_as_removed() -> None:
    event = parse_neighbor_event(
        "192.168.1.25 dev wlan0 lladdr AA:BB:CC:DD:EE:FF FAILED"
    )
    assert event is not None
    assert event.kind == "removed"



def test_parse_ipv6_neighbor_event() -> None:
    event = parse_neighbor_event(
        "fe80::1234 dev wlan0 lladdr AA:BB:CC:DD:EE:FF STALE"
    )
    assert event is not None
    assert event.address == "fe80::1234"
    assert event.mac == "aa:bb:cc:dd:ee:ff"
    assert event.kind == "changed"


@pytest.mark.parametrize("state", ["STALE", "DELAY", "PROBE", "PERMANENT", "NOARP", "NONE", "INCOMPLETE", ""])
@pytest.mark.parametrize("prefix", ["", "Added ", "New "])
def test_cache_creation_and_unconfirmed_states_only_request_reconciliation(state, prefix):
    event = parse_neighbor_event(
        f"{prefix}192.168.1.25 dev wlan0 lladdr AA:BB:CC:DD:EE:FF router {state}"
    )
    assert event.kind == "changed"


@pytest.mark.parametrize("flags", ["router REACHABLE", "REACHABLE router", "reachable managed"])
def test_reachable_neighbor_flags_do_not_hide_confirmation(flags):
    event = parse_neighbor_event(f"192.168.1.25 dev wlan0 lladdr AA:BB:CC:DD:EE:FF {flags}")
    assert event.kind == "added"


def test_deleted_reachable_entry_remains_a_removal_hint():
    event = parse_neighbor_event("Deleted 192.168.1.25 dev wlan0 lladdr AA:BB:CC:DD:EE:FF REACHABLE")
    assert event.kind == "removed"


def test_interface_named_reachable_is_not_a_confirmation():
    event = parse_neighbor_event("192.168.1.25 dev reachable lladdr AA:BB:CC:DD:EE:FF STALE")
    assert event.kind == "changed"



def test_presence_monitor_stop_kills_unresponsive_child_and_joins_reader(monkeypatch) -> None:
    import subprocess
    import threading

    from network.presence import PresenceMonitor

    child_ready = threading.Event()
    reader_started = threading.Event()
    child_exit = threading.Event()

    class BlockingStdout:
        def __iter__(self):
            return self

        def __next__(self):
            reader_started.set()
            child_exit.wait(timeout=2)
            raise StopIteration

        def close(self) -> None:
            pass

    class UnresponsiveChild:
        def __init__(self) -> None:
            self.stdout = BlockingStdout()
            self.returncode = None
            self.terminate_called = False
            self.kill_called = False
            self.wait_calls = 0

        def terminate(self) -> None:
            self.terminate_called = True

        def wait(self, timeout=None) -> int:
            self.wait_calls += 1
            if timeout is not None:
                raise subprocess.TimeoutExpired("ip monitor neigh", timeout)
            self.returncode = -9
            return self.returncode

        def kill(self) -> None:
            self.kill_called = True
            self.returncode = -9
            child_exit.set()

        def poll(self):
            return self.returncode

    child = UnresponsiveChild()

    def fake_popen(*_args, **_kwargs):
        child_ready.set()
        return child

    monkeypatch.setattr("network.presence.subprocess.Popen", fake_popen)
    monitor = PresenceMonitor(lambda _event: None)
    monitor.start()
    assert child_ready.wait(timeout=2)
    assert reader_started.wait(timeout=2)

    monitor.stop()

    assert child.terminate_called
    assert child.kill_called
    assert not monitor.running
