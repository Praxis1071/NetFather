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

        # Snapshot the current managed set before writing, when the backend
        # supports read-back.  A missing table on first install is allowed:
        # the nftables create transaction itself is atomic.
        previous_blocked = None
        snapshot_error = None
        can_read_state = callable(getattr(self.backend, "read_blocked_ips", None))
        if should_apply and self.config.firewall.rollback_on_error and can_read_state:
            try:
                previous_blocked = tuple(
                    normalize_local_ips(self.backend.read_blocked_ips())
                )
            except Exception as snapshot_exc:
                snapshot_error = str(snapshot_exc)

        try:
            result = self.backend.apply(blocked, apply=should_apply)
            if should_apply and result.applied and can_read_state:
                expected = tuple(normalize_local_ips(blocked))
                actual = tuple(normalize_local_ips(self.backend.read_blocked_ips()))
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
                recovery_error = None
                if previous_blocked is None:
                    recovery_error = (
                        "Önceki firewall durumu güvenilir biçimde okunamadığı için "
                        "otomatik geri yükleme yapılmadı; mevcut kernel durumu belirsiz olabilir ve ayrıca doğrulanmalıdır."
                    )
                    if snapshot_error:
                        recovery_error += f" Okuma hatası: {snapshot_error}"
                    elif not can_read_state:
                        recovery_error += " Backend read_blocked_ips() desteklemiyor."
                else:
                    try:
                        current = tuple(
                            normalize_local_ips(self.backend.read_blocked_ips())
                        )
                        if current != previous_blocked:
                            self.backend.apply(list(previous_blocked), apply=True)
                            restored = tuple(
                                normalize_local_ips(self.backend.read_blocked_ips())
                            )
                            if restored != previous_blocked:
                                raise RuntimeError(
                                    "Geri yükleme doğrulaması başarısız: "
                                    f"expected={previous_blocked!r}, actual={restored!r}"
                                )
                    except Exception as recovery_exc:
                        recovery_error = str(recovery_exc)
                if recovery_error:
                    EventManager(self.db).record(
                        "firewall_recovery_error",
                        recovery_error,
                        severity="error",
                        metadata={
                            "backend": self.backend.name,
                            "previous_blocked": (
                                list(previous_blocked)
                                if previous_blocked is not None
                                else None
                            ),
                            "snapshot_error": snapshot_error,
                            "original_error": str(exc),
                        },
                    )
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

    def detect_drift(self) -> bool:
        """Return whether kernel firewall state differs from effective policy.

        This is observation-only: it never changes nftables state. Callers can
        schedule this check independently from policy synchronization so an
        external change is detectable between enforcement writes.
        """
        if not hasattr(self.backend, "read_blocked_ips"):
            return False

        requested_blocked = PolicyEngine(self.db).blocked_ips()
        protected = self._protected_ips()
        expected = tuple(normalize_local_ips(
            [ip for ip in requested_blocked if ip not in protected]
        ))
        try:
            actual = self.backend.read_blocked_ips()
            read_error = None
        except Exception as exc:
            actual = None
            read_error = str(exc)

        drifted = read_error is not None or actual != expected
        if drifted:
            EventManager(self.db).record(
                "firewall_drift",
                "Kernel firewall state differs from effective policy.",
                severity="error",
                metadata={
                    "backend": self.backend.name,
                    "expected": list(expected),
                    "actual": list(actual) if actual is not None else None,
                    "read_error": read_error,
                    "timestamp": utc_now().isoformat(),
                },
            )
        return drifted

    def rollback(self, *, apply: bool = False):
        result = self.backend.rollback(apply=apply)
        EventManager(self.db).record(
            "firewall_rollback",
            result.detail,
            metadata={"backend": result.backend, "applied": result.applied},
        )
        return result
