"""Deterministic effective policy from one consistent database read snapshot."""
from __future__ import annotations
from dataclasses import dataclass
import datetime as dt
import ipaddress
from sqlalchemy import select
from core.database import Database
from core.exceptions import DeviceNotFoundError, ValidationError
from models.device import Device
from models.profile import Profile
from models.rule import Rule
from models.policy_group import PolicyGroup, ProfileAssignment, GroupRule
from manager.schedules import active, next_change, utc_instant

@dataclass(frozen=True)
class DevicePolicy:
    device_id: int
    name: str
    mac: str
    ip: str | None
    online: bool
    allowed: bool
    reason: str
    enforcement_eligible: bool = True
    explanation: str = ""
    active_rules: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    next_transition: dt.datetime | None = None


def rule_key(rule):
    return f"{'group-rule' if isinstance(rule, GroupRule) else 'rule'}:{rule.id}"


def decision(profiles, rules, when):
    enabled = []
    invalid = []
    for rule in rules:
        if not rule.enabled:
            continue
        try:
            if active(rule.schedule, when, timezone=rule.timezone, weekdays=rule.weekdays):
                enabled.append(rule)
        except ValidationError:
            invalid.append(rule_key(rule))
    enabled.sort(key=lambda rule: (-rule.priority, isinstance(rule, GroupRule), rule.id))
    blocked = next((profile for profile in profiles if profile.internet_mode == "blocked"), None)
    controlled = next((profile for profile in profiles if profile.internet_mode == "controlled"), None)
    block = next((rule for rule in enabled if rule.action == "block"), None)
    allow = next((rule for rule in enabled if rule.action == "allow"), None)
    conflicts = []
    if block and allow:
        conflicts.append(f"{rule_key(block)} overrides {rule_key(allow)}: block-over-allow precedence.")
    if invalid:
        conflicts.append("Invalid enabled rules require review: " + ", ".join(invalid))
    if blocked:
        allowed, reason = False, f"profile:{blocked.name}=blocked"
    elif block:
        allowed, reason = False, f"{rule_key(block)}=block"
    elif controlled:
        allowed = bool(allow)
        reason = f"profile:{controlled.name}=controlled;" + (f"{rule_key(allow)}=allow" if allow else "default-deny")
    elif allow:
        allowed, reason = True, f"{rule_key(allow)}=allow"
    else:
        allowed, reason = True, "default-allow"
    return allowed, reason, enabled, tuple(conflicts), invalid


class PolicyEngine:
    """Blocked profile > any active block > allow > controlled default deny.

    Priority chooses the winning rule within an action; it cannot bypass an
    explicit block. Ties are stable by device/group scope and persistent rule ID.
    """
    def __init__(self, db: Database):
        self.db = db

    def _evaluate(self, session, device, when):
        profiles = list(session.scalars(select(Profile).where(Profile.device_id == device.id).order_by(Profile.id)))
        assignment = session.get(ProfileAssignment, device.id)
        rules = list(session.scalars(select(Rule).where(Rule.device_id == device.id)))
        if assignment:
            profiles.append(session.get(PolicyGroup, assignment.profile_id))
            rules.extend(session.scalars(select(GroupRule).where(GroupRule.profile_id == assignment.profile_id)))
        allowed, reason, enabled, conflicts, invalid = decision(profiles, rules, when)
        duplicate = device.ip and session.scalar(select(Device.id).where(Device.id != device.id, Device.ip == device.ip))
        if duplicate:
            conflicts += ("Another registered identity claims the selected IP; enforcement is excluded pending review.",)
        try:
            address = ipaddress.ip_address(device.ip) if device.ip else None
            invalid_address = False
        except ValueError:
            address, invalid_address = None, True
            conflicts += ("Stored address is invalid; review required before enforcement.",)
        scoped_ipv6 = bool(address and address.version == 6 and address.is_link_local)
        if scoped_ipv6:
            conflicts += ("Link-local IPv6 requires an interface-qualified enforcement path; this backend cannot enforce it safely.",)
        transition = None
        if not any(profile.internet_mode == "blocked" for profile in profiles):
            cursor, limit = when, when + dt.timedelta(days=8)
            # Follow actual rule transitions until the effective decision changes.
            for _ in range(2048):
                candidates = []
                for rule in rules:
                    try:
                        change = next_change(rule, cursor)
                    except ValidationError:
                        continue
                    if change and change <= limit:
                        candidates.append(change)
                if not candidates:
                    break
                cursor = min(candidates)
                if decision(profiles, rules, cursor)[0] != allowed:
                    transition = cursor
                    break
        explanation = ("Access allowed. " if allowed else "Access denied. ") + reason + ". " + (
            "Block rules override allow rules; higher priority wins within the same action. "
            "Controlled profiles deny access unless an allow window is active. "
            "Schedules use their configured IANA time zone; overnight windows belong to the starting weekday.")
        return DevicePolicy(device.id, device.name, device.mac, device.ip, bool(device.online), allowed, reason,
            not device.identity_conflict and not invalid and not duplicate and not scoped_ipv6 and not invalid_address, explanation, tuple(rule_key(rule) for rule in enabled), conflicts, transition)

    def evaluate_device(self, device_name, *, when=None):
        when = utc_instant(when)
        with self.db.session() as session:
            session.connection().exec_driver_sql("BEGIN")
            device = session.scalar(select(Device).where(Device.name == device_name))
            if device is None:
                raise DeviceNotFoundError(f"Device not found: {device_name}")
            return self._evaluate(session, device, when)

    def evaluate_all(self, *, when=None):
        when = utc_instant(when)
        with self.db.session() as session:
            session.connection().exec_driver_sql("BEGIN")
            return [self._evaluate(session, device, when) for device in session.scalars(select(Device).order_by(Device.id))]

    def blocked_ips(self):
        return sorted({policy.ip for policy in self.evaluate_all() if not policy.allowed and policy.ip and policy.enforcement_eligible})
