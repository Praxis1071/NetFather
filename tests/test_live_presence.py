"""Regression tests for live-presence reconciliation concurrency and shutdown."""
from __future__ import annotations

import threading
import time

from network.live_presence import LivePresenceService


class _Monitor:
    running = True

    def __init__(self, _callback) -> None:
        self.stopped = False

    def start(self) -> bool:
        return True

    def stop(self) -> None:
        self.stopped = True


class _DeviceManager:
    def __init__(self, _database) -> None:
        pass


class _Discovery:
    def __init__(self, *, device_manager) -> None:
        self.running = False
        self.scan_calls = 0
        self.active_scans = 0
        self.max_active_scans = 0
        self.lock = threading.Lock()
        self.scan_impl = None

    def scan(self, **_kwargs):
        with self.lock:
            self.scan_calls += 1
            self.active_scans += 1
            self.max_active_scans = max(self.max_active_scans, self.active_scans)
        try:
            if self.scan_impl is not None:
                return self.scan_impl()
            time.sleep(0.03)
            return object()
        finally:
            with self.lock:
                self.active_scans -= 1


def _service(monkeypatch) -> LivePresenceService:
    monkeypatch.setattr("network.live_presence.DeviceManager", _DeviceManager)
    monkeypatch.setattr("network.live_presence.DiscoveryService", _Discovery)
    monkeypatch.setattr("network.live_presence.PresenceMonitor", _Monitor)
    service = LivePresenceService(object(), on_reconciled=None)
    service._stopped = False
    # Avoid real recurring timers in unit tests.
    monkeypatch.setattr(service, "_schedule_periodic_safety_scan", lambda: None)
    return service


def test_live_reconciliation_is_single_flight(monkeypatch) -> None:
    service = _service(monkeypatch)
    first = threading.Thread(target=service._reconcile)
    second = threading.Thread(target=service._reconcile)

    first.start()
    second.start()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert service.discovery.scan_calls == 2
    assert service.discovery.max_active_scans == 1


def test_reconciliation_failure_keeps_safety_path_scheduled(monkeypatch) -> None:
    service = _service(monkeypatch)
    scheduled: list[bool] = []
    service.discovery.scan_impl = lambda: (_ for _ in ()).throw(RuntimeError("scan failed"))
    monkeypatch.setattr(
        service, "_schedule_periodic_safety_scan", lambda: scheduled.append(True)
    )

    service._reconcile()

    assert scheduled == [True]


def test_stop_waits_for_in_flight_reconciliation(monkeypatch) -> None:
    service = _service(monkeypatch)
    scan_started = threading.Event()
    release_scan = threading.Event()
    stop_returned = threading.Event()

    def blocked_scan():
        scan_started.set()
        assert release_scan.wait(timeout=2)
        return object()

    service.discovery.scan_impl = blocked_scan
    scan_thread = threading.Thread(target=service._reconcile)
    scan_thread.start()
    assert scan_started.wait(timeout=2)

    stop_thread = threading.Thread(target=lambda: (service.stop(), stop_returned.set()))
    stop_thread.start()
    assert not stop_returned.wait(timeout=0.05)

    release_scan.set()
    scan_thread.join(timeout=2)
    stop_thread.join(timeout=2)

    assert not scan_thread.is_alive()
    assert not stop_thread.is_alive()
    assert stop_returned.is_set()
    assert service.monitor.stopped
