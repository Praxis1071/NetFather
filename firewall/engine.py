"""Policy-to-firewall integration with management-path safety guards."""
from __future__ import annotations

from core.config import Config
from core.database import Database
from core.time_utils import utc_now
from manager.event_manager import EventManager
from manager.policy_engine import PolicyEngine
from firewall.backends import get_firewall_backend
from network.interface import get_network_status


class FirewallEngine:
    """Synchronize effective policy to the selected Linux firewall backend."""

    def __init__(self, db: Database, config: Config) -> None:
        self.db, self.config = db, config
        self.backend = get_firewall_backend(config.firewall.backend)

    @staticmethod
    def _protected_ips() -> set[str]:
        """Return local management-path IPv4 addresses that must never be blocked."""
        status = get_network_status()
        return {
            value
            for value in (status.local_ip, status.gateway)
            if value
        }

    def sync(self, *, apply: bool | None = None):
        should_apply = self.config.firewall.enforcement_enabled if apply is None else apply
        requested_blocked = PolicyEngine(self.db).blocked_ips()
        protected = self._protected_ips()
        blocked = [ip for ip in requested_blocked if ip not in protected]

        try:
            result = self.backend.apply(blocked, apply=should_apply)
        except Exception as exc:
            EventManager(self.db).record(
                "firewall_error",
                str(exc),
                severity="error",
                metadata={"backend": self.backend.name},
            )
            if should_apply and self.config.firewall.rollback_on_error:
                try:
                    self.backend.rollback(apply=True)
                except Exception:
                    pass
            raise

        EventManager(self.db).record(
            "firewall_sync",
            result.detail,
            metadata={
                "backend": result.backend,
                "blocked": list(result.blocked_ips),
                "requested_blocked": requested_blocked,
                "protected": sorted(protected),
                "applied": result.applied,
                "timestamp": utc_now().isoformat(),
            },
        )
        return result

    def rollback(self, *, apply: bool = False):
        result = self.backend.rollback(apply=apply)
        EventManager(self.db).record(
            "firewall_rollback",
            result.detail,
            metadata={"backend": result.backend, "applied": result.applied},
        )
        return result
