"""Policy-to-firewall integration."""
from __future__ import annotations
from core.config import Config
from core.database import Database
from manager.event_manager import EventManager
from manager.policy_engine import PolicyEngine
from firewall.backends import get_firewall_backend

class FirewallEngine:
    def __init__(self, db: Database, config: Config) -> None:
        self.db, self.config = db, config
        self.backend = get_firewall_backend(config.firewall.backend)
    def sync(self, *, apply: bool | None = None):
        should_apply = self.config.firewall.enforcement_enabled if apply is None else apply
        blocked = PolicyEngine(self.db).blocked_ips()
        try:
            result = self.backend.apply(blocked, apply=should_apply)
        except Exception as exc:
            EventManager(self.db).record("firewall_error", str(exc), severity="error", metadata={"backend": self.backend.name})
            if should_apply and self.config.firewall.rollback_on_error:
                try: self.backend.rollback(apply=True)
                except Exception: pass
            raise
        EventManager(self.db).record("firewall_sync", result.detail, metadata={"backend": result.backend, "blocked": list(result.blocked_ips), "applied": result.applied})
        return result
    def rollback(self, *, apply: bool = False):
        result = self.backend.rollback(apply=apply)
        EventManager(self.db).record("firewall_rollback", result.detail, metadata={"backend": result.backend, "applied": result.applied})
        return result
