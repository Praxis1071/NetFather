"""CRUD and schedule evaluation for device access rules.

This module manages rule *data* and determines whether a rule is active at a
given local wall-clock time. Applying firewall/nftables changes is deliberately
kept out of this layer and remains a later phase.
"""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from core.database import Database
from core.exceptions import RuleNotFoundError, ValidationError
from core.logger import get_logger
from manager.device_manager import DeviceManager
from models.rule import Rule

log = get_logger("rule_manager")

VALID_ACTIONS = frozenset({"allow", "block"})
_SCHEDULE_PATTERN = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


def normalize_schedule(schedule: str) -> str:
    """Validate and normalize ``H:MM-HH:MM`` to ``HH:MM-HH:MM``."""
    match = _SCHEDULE_PATTERN.fullmatch(schedule)
    if match is None:
        raise ValidationError("Schedule 'HH:MM-HH:MM' formatında olmalıdır.")
    sh, sm, eh, em = (int(value) for value in match.groups())
    if sh > 23 or eh > 23 or sm > 59 or em > 59:
        raise ValidationError("Schedule geçerli bir 24 saat zamanı içermelidir.")
    return f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"


def schedule_is_active(schedule: str, when: dt.datetime | dt.time | None = None) -> bool:
    """Return whether ``schedule`` is active at ``when``.

    Windows that cross midnight are supported (for example ``22:00-07:00``).
    Equal start/end times represent a full-day window.
    """
    normalized = normalize_schedule(schedule)
    start_text, end_text = normalized.split("-", 1)
    start = dt.time.fromisoformat(start_text)
    end = dt.time.fromisoformat(end_text)

    if when is None:
        current = dt.datetime.now().time().replace(second=0, microsecond=0)
    elif isinstance(when, dt.datetime):
        current = when.time().replace(second=0, microsecond=0)
    else:
        current = when.replace(second=0, microsecond=0)

    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


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
        device_name: str,
        action: str,
        schedule: str,
        *,
        enabled: bool = True,
        description: str | None = None,
    ) -> Rule:
        normalized_action = self._validate_action(action)
        normalized_schedule = normalize_schedule(schedule)
        cleaned_description = description.strip() if description else None
        if cleaned_description and len(cleaned_description) > 256:
            raise ValidationError("Kural açıklaması en fazla 256 karakter olabilir.")

        with self.db.session() as session:
            device = DeviceManager._require_by_name(session, device_name)
            rule = Rule(
                device_id=device.id,
                action=normalized_action,
                schedule=normalized_schedule,
                enabled=enabled,
                description=cleaned_description,
            )
            session.add(rule)
            session.flush()
            session.refresh(rule)
            rule.device = device
            session.expunge(rule)
            log.info("Kural oluşturuldu: device=%s rule=%s", device.name, rule.id)
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

    def set_enabled(self, rule_id: int, enabled: bool) -> Rule:
        with self.db.session() as session:
            rule = session.get(Rule, rule_id)
            if rule is None:
                raise RuleNotFoundError(f"Kural bulunamadı: id={rule_id}")
            rule.enabled = enabled
            session.flush()
            session.refresh(rule)
            session.expunge(rule)
            log.info("Kural durumu değiştirildi: id=%s enabled=%s", rule_id, enabled)
            return rule

    def delete_rule(self, rule_id: int) -> None:
        with self.db.session() as session:
            rule = session.get(Rule, rule_id)
            if rule is None:
                raise RuleNotFoundError(f"Kural bulunamadı: id={rule_id}")
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
                if schedule_is_active(rule.schedule, when):
                    active.append(rule)
            except ValidationError:
                # Legacy/manual DB edits should not make every rule query fail.
                log.warning("Geçersiz schedule içeren kural atlandı: id=%s", rule.id)
        return active
