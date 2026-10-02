from pathlib import Path

from core.database import Database
from manager.device_service import DeviceService


def make_database(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'netfather.db'}")
    database.init_db()
    return database


def test_device_service_updates_and_renames_device(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    try:
        service = DeviceService(database)
        service.manager.add_device("Phone", "AA:BB:CC:DD:EE:FF", ip="192.168.1.20", device_type="phone")

        snapshot = service.update(
            "Phone",
            new_name="My Phone",
            ip="192.168.1.25",
            vendor="Example",
            device_type="phone",
        )

        device = snapshot.devices[0]
        assert snapshot.selected_name == "My Phone"
        assert device.name == "My Phone"
        assert device.ip == "192.168.1.25"
        assert device.vendor == "Example"
    finally:
        database.close()


def test_device_service_deletes_device(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    try:
        service = DeviceService(database)
        service.manager.add_device("Phone", "AA:BB:CC:DD:EE:FF")
        snapshot = service.delete("Phone")
        assert snapshot.devices == ()
    finally:
        database.close()
