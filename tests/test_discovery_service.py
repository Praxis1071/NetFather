from datetime import datetime, timezone

from network.discovery import DiscoveredHost
from network.discovery_service import DiscoveryService


def test_discovery_service_reconciles_observations(monkeypatch) -> None:
    observed_at = datetime(2026, 9, 16, tzinfo=timezone.utc)
    hosts = [
        DiscoveredHost(
            ip="192.168.1.20",
            mac="AA-BB-CC-DD-EE-FF",
            hostname="phone",
            vendor="Example",
            source="active+passive",
        )
    ]
    monkeypatch.setattr("network.discovery_service.scan_network", lambda *args, **kwargs: hosts)
    service = DiscoveryService()
    snapshot = service.scan(mode="hybrid")

    assert snapshot.error is None
    assert snapshot.scanned == 1
    identity = snapshot.identities[0]
    assert identity.mac == "AA:BB:CC:DD:EE:FF"
    assert identity.current_ip == "192.168.1.20"
    assert identity.online is True


def test_discovery_service_is_single_flight(monkeypatch) -> None:
    service = DiscoveryService()
    service._running = True

    try:
        service.scan()
    except RuntimeError as exc:
        assert "zaten çalışıyor" in str(exc)
    else:
        raise AssertionError("Concurrent discovery should be rejected")


def test_discovery_service_subscription_can_change_during_callback() -> None:
    service = DiscoveryService()
    calls: list[str] = []
    holder: dict[str, object] = {}

    def first(_snapshot) -> None:
        calls.append("first")
        unsubscribe = holder.get("unsubscribe")
        if callable(unsubscribe):
            unsubscribe()

    holder["unsubscribe"] = service.subscribe(first)
    service.subscribe(lambda _snapshot: calls.append("second"))

    snapshot = service._snapshot
    assert snapshot is None

    # Exercise the listener dispatch without invoking an external scan.
    service._snapshot = type("Snapshot", (), {})()
    with service._lock:
        listeners = tuple(service._listeners)
    for callback in listeners:
        callback(service._snapshot)

    with service._lock:
        remaining = tuple(service._listeners)

    assert calls == ["first", "second"]
    assert len(remaining) == 1
