from __future__ import annotations

from pathlib import Path

import pytest

from core.database import Database
from core.exceptions import DuplicateProfileError, ProfileNotFoundError, ValidationError
from manager.device_manager import DeviceManager
from manager.profile_manager import ProfileManager


@pytest.fixture
def managers(tmp_path: Path):
    db = Database(tmp_path / "profiles.db")
    db.init_db()
    devices = DeviceManager(db)
    profiles = ProfileManager(db)
    devices.add_device("Tablet", "AA:BB:CC:DD:EE:01")
    yield devices, profiles
    db.close()


def test_create_and_list_profile(managers) -> None:
    _, profiles = managers
    created = profiles.create_profile("Tablet", "Child", "controlled")
    assert created.id is not None
    assert created.device.name == "Tablet"
    assert created.internet_mode == "controlled"
    listed = profiles.list_profiles("Tablet")
    assert [(item.name, item.internet_mode) for item in listed] == [("Child", "controlled")]


def test_duplicate_profile_name_on_same_device_rejected(managers) -> None:
    _, profiles = managers
    profiles.create_profile("Tablet", "Child")
    with pytest.raises(DuplicateProfileError):
        profiles.create_profile("Tablet", "Child")


def test_invalid_mode_rejected(managers) -> None:
    _, profiles = managers
    with pytest.raises(ValidationError):
        profiles.create_profile("Tablet", "Child", "magic")


def test_set_mode_and_delete(managers) -> None:
    _, profiles = managers
    created = profiles.create_profile("Tablet", "Child")
    updated = profiles.set_mode(created.id, "blocked")
    assert updated.internet_mode == "blocked"
    profiles.delete_profile(created.id)
    with pytest.raises(ProfileNotFoundError):
        profiles.get_profile(created.id)
