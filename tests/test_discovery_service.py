from datetime import datetime, timezone

from network.discovery import DiscoveredHost, DiscoveryReport
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
    monkeypatch.setattr("network.discovery_service.scan_network_report", lambda *args, **kwargs: DiscoveryReport(tuple(hosts)))
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


def test_discovery_service_subscription_can_change_during_callback(monkeypatch) -> None:
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
    monkeypatch.setattr("network.discovery_service.scan_network_report", lambda *args, **kwargs: DiscoveryReport())

    snapshot = service.scan(mode="passive")

    assert snapshot.error is None
    assert calls == ["first", "second"]
    with service._lock:
        assert len(service._listeners) == 1


def test_discovery_listener_failure_does_not_fail_scan_or_skip_other_listeners(monkeypatch) -> None:
    service = DiscoveryService()
    calls: list[str] = []
    service.subscribe(lambda _snapshot: (_ for _ in ()).throw(RuntimeError("listener failed")))
    service.subscribe(lambda _snapshot: calls.append("second"))
    monkeypatch.setattr("network.discovery_service.scan_network_report", lambda *args, **kwargs: DiscoveryReport())

    snapshot = service.scan(mode="passive")

    assert snapshot.error is None
    assert snapshot.scanned == 0
    assert calls == ["second"]
