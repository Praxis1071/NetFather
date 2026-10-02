"""Application-facing policy snapshots shared by GTK workspaces.

The GUI should never reimplement policy precedence. This service turns the
backend PolicyEngine into a small, immutable snapshot that can be refreshed in
a worker thread and rendered safely by GTK on the main thread.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.database import Database
from manager.policy_engine import DevicePolicy, PolicyEngine


@dataclass(frozen=True)
class PolicySnapshot:
    """Point-in-time effective policy state for the local network."""

    devices: tuple[DevicePolicy, ...]
    allowed: int
    blocked: int
    online: int
    blocked_ips: tuple[str, ...]


class PolicyService:
    """Read-only application service for effective device policies."""

    def __init__(self, db: Database) -> None:
        self.engine = PolicyEngine(db)

    def refresh(self) -> PolicySnapshot:
        policies = tuple(self.engine.evaluate_all())
        return PolicySnapshot(
            devices=policies,
            allowed=sum(1 for policy in policies if policy.allowed),
            blocked=sum(1 for policy in policies if not policy.allowed),
            online=sum(1 for policy in policies if policy.online),
            blocked_ips=tuple(sorted({policy.ip for policy in policies if not policy.allowed and policy.ip})),
        )

    def evaluate_device(self, device_name: str) -> DevicePolicy:
        return self.engine.evaluate_device(device_name)
