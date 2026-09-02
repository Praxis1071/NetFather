from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from core.database import Database
from core.exceptions import RuleNotFoundError, ValidationError
from manager.device_manager import DeviceManager
from manager.rule_manager import RuleManager, normalize_schedule, schedule_is_active


@pytest.fixture
def manager(tmp_path: Path):
    db = Database(tmp_path / "rules.db")
    db.init_db()
    DeviceManager(db).add_device("Phone", "AA:BB:CC:DD:EE:02")
    rules = RuleManager(db)
    yield rules
    db.close()


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [("8:05-9:30", "08:05-09:30"), ("22:00 - 07:00", "22:00-07:00")],
)
def test_normalize_schedule(raw: str, normalized: str) -> None:
    assert normalize_schedule(raw) == normalized


@pytest.mark.parametrize("bad", ["", "25:00-07:00", "12:60-13:00", "hello", "12-13"])
def test_invalid_schedule_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        normalize_schedule(bad)


def test_schedule_evaluation_day_and_overnight() -> None:
    assert schedule_is_active("09:00-17:00", dt.time(9, 0))
    assert not schedule_is_active("09:00-17:00", dt.time(17, 0))
    assert schedule_is_active("22:00-07:00", dt.time(23, 0))
    assert schedule_is_active("22:00-07:00", dt.time(6, 59))
    assert not schedule_is_active("22:00-07:00", dt.time(12, 0))
    assert schedule_is_active("00:00-00:00", dt.time(12, 0))


def test_create_list_enable_disable_and_active(manager: RuleManager) -> None:
    rule = manager.create_rule("Phone", "block", "22:00-07:00", description="night")
    assert rule.device.name == "Phone"
    assert rule.schedule == "22:00-07:00"
    assert [item.id for item in manager.active_rules(when=dt.time(23, 0))] == [rule.id]

    manager.set_enabled(rule.id, False)
    assert manager.active_rules(when=dt.time(23, 0)) == []
    manager.set_enabled(rule.id, True)
    assert manager.get_rule(rule.id).enabled is True


def test_delete_missing_rule_raises(manager: RuleManager) -> None:
    with pytest.raises(RuleNotFoundError):
        manager.delete_rule(999)


def test_active_rules_skips_invalid_legacy_schedule(manager: RuleManager) -> None:
    from models.rule import Rule

    with manager.db.session() as session:
        from models.device import Device
        device = session.query(Device).filter_by(name="Phone").one()
        session.add(Rule(device_id=device.id, action="block", schedule="broken", enabled=True))

    assert manager.active_rules(when=dt.time(12, 0)) == []
