"""Tests for the non-blocking TUI discovery controller."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import tui.scan as scan_module
from network.discovery import DiscoveredHost
from tui.scan import ScanController, ScanStatus


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        database_path="/tmp/netfather-test.db",
        network=SimpleNamespace(scan_timeout_seconds=5),
        discovery=SimpleNamespace(
            mode="active",
            subnet="192.168.1.0/24",
            active_timeout_seconds=2,
            hostname_resolution=True,
            vendor_detection=True,
            os_detection=True,
            auto_register=True,
            offline_after_seconds=60,
        ),
    )


def test_scan_options_are_captured_from_config() -> None:
    options = scan_module.ScanOptions.from_config(_config())
    assert options.mode == "active"
    assert options.subnet == "192.168.1.0/24"
    assert options.hostname_resolution is True
    assert options.vendor_detection is True
    assert options.os_detection is True


def test_controller_does_not_block_and_supports_cancellation(monkeypatch) -> None:
    controller = ScanController()
    started = threading.Event()
    release = threading.Event()

    def fake_scan_network(**_kwargs):
        started.set()
        release.wait(timeout=2)
        return [DiscoveredHost(ip="192.168.1.20", mac="aa:bb:cc:dd:ee:ff")]

    monkeypatch.setattr(scan_module, "scan_network", fake_scan_network)
    monkeypatch.setattr(
        controller,
        "_reconcile",
        lambda hosts, config: (1, 0, 0),
    )

    assert controller.start(_config()) is True
    assert started.wait(timeout=1)
    assert controller.snapshot().status in {ScanStatus.SCANNING, ScanStatus.CANCELLING}

    assert controller.cancel() is True
    assert controller.snapshot().status == ScanStatus.CANCELLING

    release.set()
    deadline = time.monotonic() + 2
    while controller.snapshot().running and time.monotonic() < deadline:
        time.sleep(0.01)

    assert controller.snapshot().status == ScanStatus.CANCELLED
    controller.shutdown()


def test_controller_rejects_second_scan_while_running(monkeypatch) -> None:
    controller = ScanController()
    release = threading.Event()

    def fake_scan_network(**_kwargs):
        release.wait(timeout=2)
        return []

    monkeypatch.setattr(scan_module, "scan_network", fake_scan_network)
    monkeypatch.setattr(controller, "_reconcile", lambda hosts, config: (0, 0, 0))

    assert controller.start(_config()) is True
    assert controller.start(_config()) is False

    controller.cancel()
    release.set()
    deadline = time.monotonic() + 2
    while controller.snapshot().running and time.monotonic() < deadline:
        time.sleep(0.01)
    controller.shutdown()
