"""Tests for the TUI data aggregation layer."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

import tui.data as tui_data
from core.config import load_config
from core.database import Database
from manager.device_manager import DeviceManager
from network.discovery import DiscoveredHost
from network.interface import NetworkStatus
from tui.scan import ScanStatus
from tui.state import AppState


@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "netfather-test.db")
    database.init_db()
    yield database
    database.close()


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import core.config as config_module

    fake_data_dir = tmp_path / "data"
    monkeypatch.setattr(config_module, "DEFAULT_DATA_DIR", fake_data_dir)
    return load_config(config_path=tmp_path / "config.toml")


def test_overview_data_reflects_registered_device_count(
    config, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    DeviceManager(db).add_device(name="Laptop", mac="AA:BB:CC:DD:EE:FF")
    monkeypatch.setattr(tui_data, "get_network_status", lambda: NetworkStatus())

    data = tui_data.get_overview_data(config, db, AppState())

    assert data.registered_device_count == 1
    assert data.database_ok is True


def test_overview_data_never_fakes_network_status(
    config, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tui_data, "get_network_status", lambda: NetworkStatus())

    data = tui_data.get_overview_data(config, db, AppState())

    assert data.network_status_known is False
    assert data.interface is None
    assert data.gateway is None


def test_overview_data_reflects_real_network_status_when_available(
    config, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_status = NetworkStatus(interface="wlan0", local_ip="192.168.1.50", gateway="192.168.1.1")
    monkeypatch.setattr(tui_data, "get_network_status", lambda: fake_status)

    data = tui_data.get_overview_data(config, db, AppState())

    assert data.interface == "wlan0"
    assert data.local_ip == "192.168.1.50"
    assert data.gateway == "192.168.1.1"
    assert data.network_status_known is True


def test_overview_data_shows_previous_scan_from_state(
    config, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tui_data, "get_network_status", lambda: NetworkStatus())
    state = AppState()
    now = dt.datetime.now()
    state.last_scan_time = now
    state.last_scan_hosts = [DiscoveredHost(ip="192.168.1.5")]

    data = tui_data.get_overview_data(config, db, state)

    assert data.last_scan_time == now
    assert data.last_scan_device_count == 1


def test_get_cached_network_status_only_calls_underlying_function_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def fake_get_network_status() -> NetworkStatus:
        nonlocal call_count
        call_count += 1
        return NetworkStatus(interface="eth0")

    monkeypatch.setattr(tui_data, "get_network_status", fake_get_network_status)
    state = AppState()
    first = tui_data.get_cached_network_status(state)
    second = tui_data.get_cached_network_status(state)

    assert first == second
    assert call_count == 1


def test_invalidate_network_status_cache_forces_recompute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def fake_get_network_status() -> NetworkStatus:
        nonlocal call_count
        call_count += 1
        return NetworkStatus(interface=f"eth{call_count}")

    monkeypatch.setattr(tui_data, "get_network_status", fake_get_network_status)
    state = AppState()
    tui_data.get_cached_network_status(state)
    tui_data.invalidate_network_status_cache(state)
    tui_data.get_cached_network_status(state)

    assert call_count == 2


def test_get_discovery_data_does_not_start_a_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    state = AppState()
    state.last_scan_hosts = [DiscoveredHost(ip="192.168.1.1")]
    data = tui_data.get_discovery_data(state)

    assert data.hosts == state.last_scan_hosts
    assert "Scapy" in data.backend or "Status:" in data.backend


def test_trigger_scan_starts_background_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeController:
        def __init__(self) -> None:
            self.started = False
            self.cancelled = False

        def snapshot(self):
            return SimpleNamespace(running=self.started, status=ScanStatus.IDLE)

        def start(self, config) -> bool:
            self.started = True
            return True

        def cancel(self) -> bool:
            self.cancelled = True
            self.started = False
            return True

        def hosts(self):
            return []

    controller = FakeController()
    monkeypatch.setattr(tui_data, "get_scan_controller", lambda: controller)
    hosts, message = tui_data.trigger_scan(config=None)

    assert hosts == []
    assert message == "Scan started in background."
    assert controller.started is True


def test_trigger_scan_cancels_running_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeController:
        def snapshot(self):
            return SimpleNamespace(running=True, status=ScanStatus.SCANNING)

        def cancel(self) -> bool:
            return True

        def hosts(self):
            return [DiscoveredHost(ip="192.168.1.10")]

        def start(self, config) -> bool:
            raise AssertionError("running scan must not start another scan")

    controller = FakeController()
    monkeypatch.setattr(tui_data, "get_scan_controller", lambda: controller)

    hosts, message = tui_data.trigger_scan(config=None)

    assert hosts == [DiscoveredHost(ip="192.168.1.10")]
    assert message == "Scan stopping..."


def test_get_registered_devices_returns_db_devices(db: Database) -> None:
    DeviceManager(db).add_device(name="Laptop", mac="AA:BB:CC:DD:EE:FF")

    devices, error = tui_data.get_registered_devices(db)

    assert error is None
    assert len(devices) == 1
    assert devices[0].name == "Laptop"


def test_get_registered_devices_empty_db_returns_empty_list(db: Database) -> None:
    devices, error = tui_data.get_registered_devices(db)
    assert devices == []
    assert error is None


def test_get_config_display_rows_contains_expected_labels(config) -> None:
    labels = [label for label, _ in tui_data.get_config_display_rows(config)]
    assert "Config dosyası" in labels
    assert "Database" in labels
    assert "Scan timeout (saniye)" in labels
    assert "Vendor detection" in labels


def test_get_config_display_rows_reflects_actual_scan_timeout(config) -> None:
    rows = dict(tui_data.get_config_display_rows(config))
    assert rows["Scan timeout (saniye)"] == str(config.network.scan_timeout_seconds)


def test_get_recent_log_lines_missing_file_returns_message(config) -> None:
    lines, message = tui_data.get_recent_log_lines(config)
    assert lines == []
    assert message is not None


def test_get_recent_log_lines_returns_last_n_lines(config) -> None:
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    all_lines = [f"log satırı {i}" for i in range(30)]
    config.log_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")

    lines, message = tui_data.get_recent_log_lines(config, max_lines=10)

    assert message is None
    assert len(lines) == 10
    assert lines[-1] == "log satırı 29"
