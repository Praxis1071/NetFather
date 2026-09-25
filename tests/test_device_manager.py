"""manager.device_manager.DeviceManager için CRUD ve doğrulama testleri."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

import pytest

from core.database import Database
from core.exceptions import DeviceNotFoundError, DuplicateDeviceError, ValidationError
from manager.device_manager import DeviceManager
from models.device_observation import DeviceObservationRecord


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


def test_update_device_changes_editable_fields(manager: DeviceManager) -> None:
    manager.add_device(name="Laptop", mac="AA:BB:CC:DD:EE:10")
    updated = manager.update_device(
        "Laptop",
        new_name="Work Laptop",
        ip="192.168.1.10",
        vendor="Example",
        device_type="laptop",
    )
    assert updated.name == "Work Laptop"
    assert updated.ip == "192.168.1.10"
    assert updated.vendor == "Example"
    assert updated.device_type == "laptop"


def test_sync_discovered_hosts_updates_only_registered(manager: DeviceManager) -> None:
    from network.discovery import DiscoveredHost

    manager.add_device(name="Phone", mac="AA:BB:CC:DD:EE:11")
    count = manager.sync_discovered_hosts(
        [
            DiscoveredHost(
                ip="192.168.1.20",
                mac="aa:bb:cc:dd:ee:11",
                vendor="Vendor A",
                state="REACHABLE",
            ),
            DiscoveredHost(ip="192.168.1.21", mac="11:22:33:44:55:66", state="STALE"),
        ]
    )
    assert count == 1
    device = manager.get_device_by_name("Phone")
    assert device.ip == "192.168.1.20"
    assert device.vendor == "Vendor A"
    assert device.last_seen is not None


def test_reconcile_persists_ip_history_and_survives_database_reopen(tmp_path: Path) -> None:
    from network.discovery import DiscoveredHost

    db_path = tmp_path / "identity-history.db"
    db = Database(db_path)
    db.init_db()
    manager = DeviceManager(db)

    manager.reconcile_discovery(
        [DiscoveredHost(ip="192.168.1.20", mac="AA:BB:CC:DD:EE:20", source="active")]
    )
    manager.reconcile_discovery(
        [DiscoveredHost(ip="192.168.1.42", mac="AA:BB:CC:DD:EE:20", source="active")]
    )

    with db.session() as session:
        observations = list(
            session.scalars(
                select(DeviceObservationRecord).order_by(DeviceObservationRecord.observed_at)
            ).all()
        )
        assert [item.ip for item in observations] == ["192.168.1.20", "192.168.1.42"]

    device = manager.get_device_by_mac("AA:BB:CC:DD:EE:20")
    assert device is not None
    assert device.ip == "192.168.1.42"
    db.close()

    reopened = Database(db_path)
    reopened.init_db()
    with reopened.session() as session:
        observations = list(session.scalars(select(DeviceObservationRecord)).all())
        assert {item.ip for item in observations} == {"192.168.1.20", "192.168.1.42"}
    reopened.close()


def test_manual_ip_change_is_persisted(manager: DeviceManager) -> None:
    manager.add_device("Laptop", "AA:BB:CC:DD:EE:30", ip="192.168.1.30")

    manager.update_last_seen("AA:BB:CC:DD:EE:30", ip="192.168.1.31")

    with manager.db.session() as session:
        observations = list(
            session.scalars(
                select(DeviceObservationRecord).where(
                    DeviceObservationRecord.ip.in_(["192.168.1.30", "192.168.1.31"])
                )
            ).all()
        )
    assert {item.ip for item in observations} == {"192.168.1.30", "192.168.1.31"}


def test_delete_device_cascades_observation_history(manager: DeviceManager) -> None:
    manager.reconcile_discovery(
        [
            DiscoveredHost(
                ip="192.168.1.40",
                mac="AA:BB:CC:DD:EE:40",
                source="active",
            )
        ]
    )
    manager.delete_device("Device-DDEE40")

    with manager.db.session() as session:
        assert session.scalars(select(DeviceObservationRecord)).all() == []
