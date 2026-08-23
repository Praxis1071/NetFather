"""manager.device_manager.DeviceManager için CRUD ve doğrulama testleri."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import Database
from core.exceptions import DeviceNotFoundError, DuplicateDeviceError, ValidationError
from manager.device_manager import DeviceManager


@pytest.fixture
def manager(tmp_path: Path):
    database = Database(tmp_path / "netfather-test.db")
    database.init_db()
    yield DeviceManager(database)
    database.close()


def test_add_device_persists_and_normalizes_mac(manager: DeviceManager) -> None:
    device = manager.add_device(name="Laptop", mac="aa:bb:cc:dd:ee:ff")

    assert device.id is not None
    assert device.mac == "AA:BB:CC:DD:EE:FF"

    devices = manager.list_devices()
    assert len(devices) == 1
    assert devices[0].name == "Laptop"


def test_add_device_with_dash_separated_mac(manager: DeviceManager) -> None:
    device = manager.add_device(name="Phone", mac="AA-BB-CC-DD-EE-FF")
    assert device.mac == "AA:BB:CC:DD:EE:FF"


def test_add_device_duplicate_mac_raises(manager: DeviceManager) -> None:
    manager.add_device(name="Laptop", mac="AA:BB:CC:DD:EE:FF")
    with pytest.raises(DuplicateDeviceError):
        manager.add_device(name="Other Device", mac="AA:BB:CC:DD:EE:FF")


def test_add_device_duplicate_name_raises(manager: DeviceManager) -> None:
    manager.add_device(name="Laptop", mac="AA:BB:CC:DD:EE:FF")
    with pytest.raises(DuplicateDeviceError):
        manager.add_device(name="Laptop", mac="11:22:33:44:55:66")


def test_add_device_invalid_mac_raises_validation_error(manager: DeviceManager) -> None:
    with pytest.raises(ValidationError):
        manager.add_device(name="Broken", mac="not-a-mac-address")


def test_add_device_empty_name_raises_validation_error(manager: DeviceManager) -> None:
    with pytest.raises(ValidationError):
        manager.add_device(name="   ", mac="AA:BB:CC:DD:EE:FF")


def test_get_device_by_name_not_found_raises(manager: DeviceManager) -> None:
    with pytest.raises(DeviceNotFoundError):
        manager.get_device_by_name("Bilinmeyen Cihaz")


def test_get_device_by_mac_returns_none_when_missing(manager: DeviceManager) -> None:
    assert manager.get_device_by_mac("AA:BB:CC:DD:EE:FF") is None


def test_delete_device_removes_record(manager: DeviceManager) -> None:
    manager.add_device(name="Çocuğun Tableti", mac="AA:BB:CC:DD:EE:FF")

    manager.delete_device("Çocuğun Tableti")

    with pytest.raises(DeviceNotFoundError):
        manager.get_device_by_name("Çocuğun Tableti")
    assert manager.list_devices() == []


def test_delete_nonexistent_device_raises(manager: DeviceManager) -> None:
    with pytest.raises(DeviceNotFoundError):
        manager.delete_device("Bilinmeyen Cihaz")


def test_update_last_seen_updates_timestamp_and_ip(manager: DeviceManager) -> None:
    manager.add_device(name="Laptop", mac="AA:BB:CC:DD:EE:FF")

    manager.update_last_seen("AA:BB:CC:DD:EE:FF", ip="192.168.1.50")

    device = manager.get_device_by_name("Laptop")
    assert device.ip == "192.168.1.50"
    assert device.last_seen is not None


def test_update_last_seen_missing_device_raises(manager: DeviceManager) -> None:
    with pytest.raises(DeviceNotFoundError):
        manager.update_last_seen("AA:BB:CC:DD:EE:FF")
