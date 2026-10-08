"""Policy-to-firewall integration with management-path safety guards."""
from __future__ import annotations

from core.config import Config
from core.database import Database
from core.exceptions import ConfigError
from core.time_utils import utc_now
from manager.event_manager import EventManager
from manager.policy_engine import PolicyEngine
from firewall.backends import get_firewall_backend
from firewall.base import normalize_local_ips
from network.interface import get_local_ipv4_addresses, get_local_ipv6_addresses, get_network_status


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
            *get_local_ipv4_addresses(),
            *get_local_ipv6_addresses(),
            *{value for value in (status.local_ip, status.gateway) if value},
        }

    @staticmethod
    def _ip_forwarding_enabled() -> bool:
        try:
            with open("/proc/sys/net/ipv4/ip_forward", encoding="ascii") as handle:
                ipv4 = handle.read().strip() == "1"
            with open("/proc/sys/net/ipv6/conf/all/forwarding", encoding="ascii") as handle:
                ipv6 = handle.read().strip() == "1"
            return ipv4 and ipv6
        except OSError:
            return False

    def _validate_enforcement_topology(self) -> None:
        topology = self.config.firewall.enforcement_topology
        if topology in {"unverified", "host"}:
            raise ConfigError(
                "Gerçek ağ trafiği enforcement için firewall.enforcement_topology "
                "gateway veya inline olarak açıkça ayarlanmalıdır."
            )
        if topology == "gateway" and not self._ip_forwarding_enabled():
            raise ConfigError(
                "Gateway enforcement seçildi ancak Linux IPv4 ve IPv6 forwarding etkin değil."
            )

    def sync(self, *, apply: bool | None = None):
        should_apply = self.config.firewall.enforcement_enabled if apply is None else apply
        if should_apply:
            self._validate_enforcement_topology()
        requested_blocked = PolicyEngine(self.db).blocked_ips()
        protected = self._protected_ips()
        blocked = [ip for ip in requested_blocked if ip not in protected]

        try:
            result = self.backend.apply(blocked, apply=should_apply)
            if should_apply and result.applied and hasattr(self.backend, "read_blocked_ips"):
                expected = tuple(normalize_local_ips(blocked))
                actual = self.backend.read_blocked_ips()
                if actual != expected:
                    raise RuntimeError(
                        "nftables kernel state desired policy ile eşleşmiyor: "
                        f"expected={expected!r}, actual={actual!r}"
                    )
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
