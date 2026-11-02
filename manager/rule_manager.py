"""CRUD and schedule evaluation for device access rules.

This module manages rule *data* and determines whether a rule is active at a
given local wall-clock time. Applying firewall/nftables changes is deliberately
kept out of this layer and remains a later phase.
"""

from __future__ import annotations

import datetime as dt
import re
import json

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from core.database import Database
from core.exceptions import RuleNotFoundError, ValidationError
from core.logger import get_logger
from manager.device_manager import DeviceManager
from models.rule import Rule
from models.event import Event
from models.device import Device
from models.policy_group import GroupRule, PolicyGroup
from manager.schedules import normalize_windows, normalize_days, active, zone

log = get_logger("rule_manager")

VALID_ACTIONS = frozenset({"allow", "block"})
_SCHEDULE_PATTERN = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


def normalize_schedule(schedule: str) -> str:
    return normalize_windows(schedule)


def schedule_is_active(schedule, when=None, *, timezone="local", weekdays="0,1,2,3,4,5,6"):
    return active(schedule, when, timezone=timezone, weekdays=weekdays)


class RuleManager:
    """Manage and evaluate time-based rules for registered devices."""

    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _validate_action(action: str) -> str:
        normalized = action.strip().lower()
        if normalized not in VALID_ACTIONS:
            raise ValidationError("Kural action değeri 'allow' veya 'block' olmalıdır.")
        return normalized

    def create_rule(
        self,
        device_name: str | None,
        action: str,
        schedule: str,
        *,
        enabled: bool = True,
        description: str | None = None,
        priority: int = 0,
        timezone: str = "local",
        weekdays: str = "0,1,2,3,4,5,6",
        profile_id: int | None = None,
        ports=None,
        destination=None,
    ) -> Rule:
        if bool(device_name) == (profile_id is not None):
            raise ValidationError("Select exactly one device or reusable profile.")
        self._validate_options(priority, timezone, weekdays, ports, destination)
        normalized_action = self._validate_action(action)
        normalized_schedule = normalize_schedule(schedule)
        cleaned_description = description.strip() if description else None
        if cleaned_description and len(cleaned_description) > 256:
            raise ValidationError("Kural açıklaması en fazla 256 karakter olabilir.")

        with self.db.session() as session:
            device = DeviceManager._require_by_name(session, device_name) if device_name else None
            if profile_id is not None and session.get(PolicyGroup, profile_id) is None:
                raise ValidationError("Reusable profile no longer exists.")
            model = GroupRule if profile_id is not None else Rule
            target = {"profile_id": profile_id} if profile_id is not None else {"device_id": device.id}
            rule = model(
                **target,
                priority=priority, timezone=timezone, weekdays=normalize_days(weekdays),
                action=normalized_action,
                schedule=normalized_schedule,
                enabled=enabled,
                description=cleaned_description,
            )
            session.add(rule)
            session.add(Event(event_type="rule_created", metadata_json=json.dumps({"profile_id": profile_id}) if profile_id else None, description=f"Rule {normalized_action} {normalized_schedule} created for {device.name if device else f'profile:{profile_id}'}", device_mac=device.mac if device else None))
            session.flush()
            session.refresh(rule)
            if device is not None: rule.device = device
            session.expunge(rule)
            log.info("Rule created: target=%s rule=%s", device.name if device else profile_id, rule.id)
            return rule

    def list_rules(self, device_name: str | None = None) -> list[Rule]:
        with self.db.session() as session:
            statement = select(Rule).options(joinedload(Rule.device)).order_by(Rule.id)
            if device_name is not None:
                device = DeviceManager._require_by_name(session, device_name)
                statement = statement.where(Rule.device_id == device.id)
            rules = list(session.scalars(statement).all())
            for rule in rules:
                session.expunge(rule)
            return rules

    def get_rule(self, rule_id: int) -> Rule:
        with self.db.session() as session:
            rule = session.scalar(
                select(Rule).options(joinedload(Rule.device)).where(Rule.id == rule_id)
            )
            if rule is None:
                raise RuleNotFoundError(f"Kural bulunamadı: id={rule_id}")
            session.expunge(rule)
            return rule

    def set_enabled(self, rule_id: int, enabled: bool, *, group: bool = False) -> Rule:
        with self.db.session() as session:
            rule = session.get(GroupRule if group else Rule, rule_id)
            if rule is None:
                raise RuleNotFoundError(f"Kural bulunamadı: id={rule_id}")
            rule.enabled = enabled
            device = session.get(Device, rule.device_id) if not group else None
            session.add(Event(event_type="rule_changed", metadata_json=json.dumps({"profile_id": rule.profile_id}) if group else None, description=f"Rule {rule_id} {'enabled' if enabled else 'disabled'}", device_mac=device.mac if device else None))
            session.flush()
            session.refresh(rule)
            session.expunge(rule)
            log.info("Kural durumu değiştirildi: id=%s enabled=%s", rule_id, enabled)
            return rule

    def delete_rule(self, rule_id: int, *, group: bool = False) -> None:
        with self.db.session() as session:
            rule = session.get(GroupRule if group else Rule, rule_id)
            if rule is None:
                raise RuleNotFoundError(f"Kural bulunamadı: id={rule_id}")
            device = session.get(Device, rule.device_id) if not group else None
            session.add(Event(event_type="rule_deleted", metadata_json=json.dumps({"profile_id": rule.profile_id}) if group else None, description=f"Rule {rule_id} deleted", device_mac=device.mac if device else None))
            session.delete(rule)
            log.info("Kural silindi: id=%s", rule_id)

    def active_rules(
        self,
        *,
        when: dt.datetime | dt.time | None = None,
        device_name: str | None = None,
    ) -> list[Rule]:
        active: list[Rule] = []
        for rule in self.list_rules(device_name=device_name):
            if not rule.enabled:
                continue
            try:
                if schedule_is_active(rule.schedule, when, timezone=rule.timezone, weekdays=rule.weekdays):
                    active.append(rule)
            except ValidationError:
                # Legacy/manual DB edits should not make every rule query fail.
                log.warning("Geçersiz schedule içeren kural atlandı: id=%s", rule.id)
        return sorted(active, key=lambda rule: (-rule.priority, rule.id))

    @staticmethod
    def _validate_options(priority, timezone, weekdays, ports=None, destination=None):
        if type(priority) is not int or not 0 <= priority <= 10000:
            raise ValidationError("Priority must be an integer from 0 to 10000; higher values win within an action.")
        zone(timezone)
        normalize_days(weekdays)
        if ports or destination:
            raise ValidationError("Service/port and destination selectors are not supported by the current whole-device enforcement backend.")

    def update_rule(self, rule_id, *, action, schedule, enabled=True, description=None,
                    priority=0, timezone="local", weekdays="0,1,2,3,4,5,6", group=False,
                    ports=None, destination=None):
        action, schedule = self._validate_action(action), normalize_schedule(schedule)
        self._validate_options(priority, timezone, weekdays, ports, destination)
        description = description.strip() if description else None
        if description and len(description) > 256:
            raise ValidationError("Description is limited to 256 characters.")
        with self.db.session() as session:
            rule = session.get(GroupRule if group else Rule, rule_id)
            if rule is None:
                raise RuleNotFoundError(f"Rule no longer exists: {rule_id}")
            rule.action, rule.schedule, rule.enabled = action, schedule, enabled
            rule.description, rule.priority, rule.timezone = description, priority, timezone
            rule.weekdays = normalize_days(weekdays)
            device = session.get(Device, rule.device_id) if not group else None
            session.add(Event(event_type="rule_changed", metadata_json=json.dumps({"profile_id": rule.profile_id}) if group else None, device_mac=device.mac if device else None,
                description=f"{'Group rule' if group else 'Rule'} {rule_id}: {action} {schedule}; priority={priority}; zone={timezone}; days={rule.weekdays}"))
            session.flush()
            session.expunge(rule)
            return rule

    def all_rules(self):
        result = self.list_rules()
        for rule in result:
            rule.scope_label = f"device:{rule.device.name}"
            rule.group_rule = False
        with self.db.session() as session:
            for rule in session.scalars(select(GroupRule).order_by(GroupRule.id)):
                profile = session.get(PolicyGroup, rule.profile_id)
                rule.scope_label = f"profile:{profile.name}"
                rule.group_rule = True
                session.expunge(rule)
                result.append(rule)
        return sorted(result, key=lambda item: (-item.priority, item.group_rule, item.id))

    def conflicts(self):
        from manager.schedules import active, utc_instant
        rules = [rule for rule in self.all_rules() if rule.enabled]
        # Report simultaneous rules at their shared scope. Per-device effective
        # explanations also report inherited group/device conflicts.
        now = utc_instant()
        warnings = []
        for index, left in enumerate(rules):
            for right in rules[index + 1:]:
                if left.scope_label != right.scope_label or left.action == right.action:
                    continue
                from manager.schedules import overlaps
                try:
                    if overlaps(left, right, now):
                        warnings.append(f"{left.scope_label}: rules {left.id}/{right.id} overlap; block overrides allow.")
                except ValidationError:
                    warnings.append(f"{left.scope_label}: invalid enabled schedule requires review.")
        return tuple(warnings)
