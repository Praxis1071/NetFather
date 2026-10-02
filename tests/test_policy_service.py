from pathlib import Path

from core.database import Database
from manager.device_manager import DeviceManager
from manager.policy_service import PolicyService
from manager.profile_manager import ProfileManager
from manager.rule_manager import RuleManager


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "policy.db")
    db.init_db()
    return db


def test_policy_service_exposes_effective_counts(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    devices = DeviceManager(db)
    devices.add_device("Laptop", "02:00:00:00:00:01", ip="192.168.1.20")
    devices.add_device("Tablet", "02:00:00:00:00:02", ip="192.168.1.21")

    profiles = ProfileManager(db)
    profiles.create_profile("Tablet", "Child", internet_mode="blocked")
    RuleManager(db).create_rule("Laptop", "allow", "08:00-20:00")

    snapshot = PolicyService(db).refresh()

    assert len(snapshot.devices) == 2
    assert snapshot.allowed == 1
    assert snapshot.blocked == 1
    assert snapshot.blocked_ips == ("192.168.1.21",)
    db.close()
