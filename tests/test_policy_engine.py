from pathlib import Path

from core.database import Database
from manager.device_manager import DeviceManager
from manager.policy_engine import PolicyEngine
from manager.profile_manager import ProfileManager
from manager.rule_manager import RuleManager


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "policy-engine.db")
    db.init_db()
    return db


def test_controlled_profile_denies_without_active_allow_rule(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    DeviceManager(db).add_device("Tablet", "02:00:00:00:00:01", ip="192.168.1.21")
    ProfileManager(db).create_profile("Tablet", "Child", internet_mode="controlled")

    policy = PolicyEngine(db).evaluate_device("Tablet")

    assert policy.allowed is False
    assert policy.reason == "profile:Child=controlled;default-deny"
    assert PolicyEngine(db).blocked_ips() == ["192.168.1.21"]
    db.close()


def test_controlled_profile_allows_only_with_active_allow_rule(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    DeviceManager(db).add_device("Tablet", "02:00:00:00:00:01", ip="192.168.1.21")
    ProfileManager(db).create_profile("Tablet", "Child", internet_mode="controlled")
    rule = RuleManager(db).create_rule("Tablet", "allow", "00:00-00:00")

    policy = PolicyEngine(db).evaluate_device("Tablet")

    assert policy.allowed is True
    assert policy.reason == f"profile:Child=controlled;rule:{rule.id}=allow"
    db.close()


def test_block_rule_overrides_controlled_allow_rule(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    DeviceManager(db).add_device("Tablet", "02:00:00:00:00:01", ip="192.168.1.21")
    ProfileManager(db).create_profile("Tablet", "Child", internet_mode="controlled")
    RuleManager(db).create_rule("Tablet", "allow", "00:00-00:00")
    block = RuleManager(db).create_rule("Tablet", "block", "00:00-00:00")

    policy = PolicyEngine(db).evaluate_device("Tablet")

    assert policy.allowed is False
    assert policy.reason == f"rule:{block.id}=block"
    db.close()


def test_unrestricted_profile_allows_by_default(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    DeviceManager(db).add_device("Laptop", "02:00:00:00:00:02", ip="192.168.1.22")
    ProfileManager(db).create_profile("Laptop", "Adult", internet_mode="unrestricted")

    policy = PolicyEngine(db).evaluate_device("Laptop")

    assert policy.allowed is True
    assert policy.reason == "default-allow"
    db.close()
