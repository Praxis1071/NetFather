"""Central effective-policy evaluation for devices and profiles."""
from __future__ import annotations
from dataclasses import dataclass
from core.database import Database
from manager.device_manager import DeviceManager
from manager.profile_manager import ProfileManager
from manager.rule_manager import RuleManager

@dataclass(frozen=True)
class DevicePolicy:
    device_id: int
    name: str
    mac: str
    ip: str | None
    online: bool
    allowed: bool
    reason: str

class PolicyEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    def evaluate_device(self, device_name: str) -> DevicePolicy:
        device = DeviceManager(self.db).get_device_by_name(device_name)
        profiles = ProfileManager(self.db).list_profiles(device_name=device_name)
        rules = RuleManager(self.db).active_rules(device_name=device_name)
        blocked_profile = next((p for p in profiles if p.internet_mode == "blocked"), None)
        block_rule = next((r for r in rules if r.action == "block"), None)
        allow_rule = next((r for r in rules if r.action == "allow"), None)
        if blocked_profile:
            allowed, reason = False, f"profile:{blocked_profile.name}=blocked"
        elif block_rule:
            allowed, reason = False, f"rule:{block_rule.id}=block"
        elif allow_rule:
            allowed, reason = True, f"rule:{allow_rule.id}=allow"
        else:
            allowed, reason = True, "default-allow"
        return DevicePolicy(device.id, device.name, device.mac, device.ip, bool(device.online), allowed, reason)

    def evaluate_all(self) -> list[DevicePolicy]:
        return [self.evaluate_device(d.name) for d in DeviceManager(self.db).list_devices()]

    def blocked_ips(self) -> list[str]:
        return sorted({p.ip for p in self.evaluate_all() if not p.allowed and p.ip})
