"""Profiles -> assignments -> rules -> effective policy acceptance in SQLite."""
from datetime import datetime, UTC
from types import SimpleNamespace
import pytest
from core.database import Database
from core.exceptions import ValidationError
from manager.device_manager import DeviceManager
from manager.group_manager import GroupManager
from manager.profile_manager import ProfileManager
from manager.rule_manager import RuleManager
from manager.policy_engine import PolicyEngine
from manager.schedules import active, next_change


@pytest.fixture
def runtime(tmp_path):
    db = Database(tmp_path / "phase-three.db"); db.init_db()
    devices = DeviceManager(db)
    first = devices.add_device("Tablet", "02:00:00:00:00:20", ip="192.168.1.20")
    second = devices.add_device("Phone", "02:00:00:00:00:21", ip="192.168.1.21")
    yield db, first, second
    db.close()


def test_reusable_profile_assignment_edit_safety_history_and_restart(runtime):
    db, first, second = runtime
    groups = GroupManager(db)
    group = groups.save("Children", "controlled")
    groups.assign(group.id, first.id); groups.assign(group.id, second.id)
    assert not PolicyEngine(db).evaluate_device(first.name).allowed
    assert not PolicyEngine(db).evaluate_device(second.name).allowed
    groups.save("Family", "blocked", profile_id=group.id)
    assert PolicyEngine(db).evaluate_device(second.name).reason == "profile:Family=blocked"
    with pytest.raises(ValidationError, match="Unassign"):
        groups.delete(group.id)
    reloaded = Database(db.db_path); reloaded.init_db()
    try:
        assert len(GroupManager(reloaded).assignments(group.id)) == 2
        assert len(GroupManager(reloaded).history(group.id)) >= 4
    finally:
        reloaded.close()
    groups.unassign(group.id, first.id); groups.unassign(group.id, second.id)
    assert PolicyEngine(db).evaluate_device(first.name).allowed
    groups.delete(group.id)
    assert groups.list_profiles() == []


def test_assignment_cannot_silently_replace_another_profile(runtime):
    db, first, _ = runtime
    groups = GroupManager(db)
    a, b = groups.save("A", "blocked"), groups.save("B", "unrestricted")
    groups.assign(a.id, first.id)
    with pytest.raises(ValidationError): groups.assign(b.id, first.id)
    assert groups.list_profiles(device_id=first.id)[0].id == a.id


def test_group_and_device_rules_have_deterministic_block_priority_and_explanation(runtime):
    db, first, _ = runtime
    groups, rules = GroupManager(db), RuleManager(db)
    group = groups.save("Child", "controlled"); groups.assign(group.id, first.id)
    allow = rules.create_rule(None, "allow", "00:00-00:00", profile_id=group.id, priority=999, timezone="UTC")
    low = rules.create_rule(first.name, "block", "00:00-00:00", priority=1, timezone="UTC")
    high = rules.create_rule(first.name, "block", "00:00-00:00", priority=20, timezone="UTC")
    policy = PolicyEngine(db).evaluate_device(first.name)
    assert not policy.allowed and policy.reason == f"rule:{high.id}=block"
    assert policy.conflicts and "Block rules override" in policy.explanation
    rules.set_enabled(high.id, False)
    assert PolicyEngine(db).evaluate_device(first.name).reason == f"rule:{low.id}=block"
    rules.delete_rule(low.id)
    assert PolicyEngine(db).evaluate_device(first.name).allowed
    rules.update_rule(allow.id, group=True, action="block", schedule="00:00-00:00", timezone="UTC", priority=2)
    assert not PolicyEngine(db).evaluate_device(first.name).allowed
    rules.delete_rule(allow.id, group=True)
    assert not PolicyEngine(db).evaluate_device(first.name).allowed  # controlled default deny


def test_legacy_profile_rename_mode_and_conflict_validation(runtime):
    db, first, _ = runtime
    profiles = ProfileManager(db)
    profile = profiles.create_profile(first.name, "Old", "unrestricted")
    profiles.update_profile(profile.id, name="Updated", internet_mode="controlled")
    assert PolicyEngine(db).evaluate_device(first.name).reason == "profile:Updated=controlled;default-deny"


def test_multiple_overnight_windows_use_starting_weekday_and_named_zone():
    assert active("22:00-07:00;12:00-13:00", datetime(2026, 11, 2, 23, tzinfo=UTC), timezone="UTC", weekdays="0")
    assert active("22:00-07:00", datetime(2026, 11, 3, 6, tzinfo=UTC), timezone="UTC", weekdays="0")
    assert not active("22:00-07:00", datetime(2026, 11, 4, 6, tzinfo=UTC), timezone="UTC", weekdays="0")
    assert active("09:00-10:00", datetime(2026, 11, 2, 5, 30, tzinfo=UTC), timezone="Asia/Baku")


def test_next_effective_policy_transition_not_just_any_rule_transition(runtime):
    db, first, _ = runtime
    profiles, rules = GroupManager(db), RuleManager(db)
    group = profiles.save("Child", "controlled"); profiles.assign(group.id, first.id)
    rules.create_rule(None, "allow", "09:00-10:00;12:00-13:00", profile_id=group.id, timezone="UTC")
    when = datetime(2026, 11, 2, 8, tzinfo=UTC)
    policy = PolicyEngine(db).evaluate_device(first.name, when=when)
    assert not policy.allowed and policy.next_transition == when.replace(hour=9)
    assert PolicyEngine(db).evaluate_device(first.name, when=when.replace(hour=9)).allowed
    profiles.save("Child", "blocked", profile_id=group.id)
    assert PolicyEngine(db).evaluate_device(first.name, when=when).next_transition is None


def test_dst_gap_and_both_repeated_wall_time_folds():
    rule = SimpleNamespace(schedule="02:30-04:00", timezone="Europe/Berlin", weekdays="0,1,2,3,4,5,6", enabled=True)
    assert next_change(rule, datetime(2026, 3, 29, 0, 30, tzinfo=UTC)) == datetime(2026, 3, 29, 1, tzinfo=UTC)
    for hour in (0, 1):
        assert active("02:30-02:45", datetime(2026, 10, 25, hour, 35, tzinfo=UTC), timezone="Europe/Berlin")


@pytest.mark.parametrize("options", [{"ports": "443"}, {"destination": "192.168.1.0/24"}, {"timezone": "Missing/Zone"}, {"priority": -1}, {"weekdays": "7"}])
def test_unsupported_selectors_and_invalid_schedules_cannot_silently_broaden_policy(runtime, options):
    db, first, _ = runtime
    with pytest.raises(ValidationError): RuleManager(db).create_rule(first.name, "block", "00:00-00:00", **options)
    assert RuleManager(db).list_rules() == []


def test_future_schedule_overlap_is_reported_at_shared_scope(runtime):
    db, first, _ = runtime
    rules = RuleManager(db)
    rules.create_rule(first.name, "allow", "22:00-07:00", timezone="UTC")
    rules.create_rule(first.name, "block", "06:00-08:00", timezone="UTC")
    assert rules.conflicts()


def test_offline_duplicate_address_is_still_unsafe_for_enforcement(runtime):
    db, first, second = runtime
    DeviceManager(db).update_device(second.name, ip=first.ip)
    GroupManager(db).assign(GroupManager(db).save("Blocked", "blocked").id, first.id)
    assert not PolicyEngine(db).evaluate_device(first.name).enforcement_eligible
    assert PolicyEngine(db).blocked_ips() == []


def test_persistent_utc_event_time_renders_correctly_in_baku():
    from core.time_utils import to_local
    from zoneinfo import ZoneInfo
    assert to_local(datetime(2026, 11, 2, 8), ZoneInfo("Asia/Baku")).hour == 12


def test_adjacent_windows_preserve_the_same_daytime_policy_for_every_minute():
    from datetime import timedelta
    base = datetime(2026, 11, 2, tzinfo=UTC)
    for minute in range(24 * 60):
        when = base + timedelta(minutes=minute)
        assert active("09:00-17:00", when, timezone="UTC") == active("09:00-12:00;12:00-17:00", when, timezone="UTC")


def test_legacy_rule_schema_upgrade_preserves_existing_policy(tmp_path):
    import sqlite3
    path = tmp_path / "legacy-rules.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE devices (id INTEGER PRIMARY KEY, name VARCHAR(128) UNIQUE, mac VARCHAR(17) UNIQUE, ip VARCHAR(45), vendor VARCHAR(128), device_type VARCHAR(32), created_at DATETIME, last_seen DATETIME)")
        connection.execute("INSERT INTO devices (id,name,mac,ip) VALUES (1,'Legacy','02:00:00:00:00:20','192.168.1.20')")
        connection.execute("CREATE TABLE rules (id INTEGER PRIMARY KEY, device_id INTEGER REFERENCES devices(id), action VARCHAR(16), schedule VARCHAR(32), enabled BOOLEAN, description VARCHAR(256))")
        connection.execute("INSERT INTO rules VALUES (1,1,'block','00:00-00:00',1,'Retained legacy rule')")
    db = Database(path); db.init_db(); db.init_db()
    try:
        rule = RuleManager(db).get_rule(1)
        assert rule.priority == 0 and rule.timezone == "local" and rule.description == "Retained legacy rule"
        assert not PolicyEngine(db).evaluate_device("Legacy").allowed
    finally:
        db.close()
