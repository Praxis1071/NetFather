"""Linux privilege and capability detection for NetFather.

The GTK process should remain unprivileged whenever possible. Network discovery
can use a mixture of unprivileged kernel state and elevated probes, while
firewall changes require a privileged mechanism. This module deliberately only
reports capabilities and never silently elevates the application.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import Enum


class PrivilegeMode(str, Enum):
    """How the current process can access privileged network operations."""

    ROOT = "root"
    USER = "user"


@dataclass(frozen=True)
class PrivilegeStatus:
    """Current process privilege facts suitable for the GTK settings UI."""

    mode: PrivilegeMode
    effective_uid: int
    is_root: bool
    pkexec_available: bool
    nft_available: bool
    ip_available: bool
    network_manager_available: bool

    @property
    def summary(self) -> str:
        if self.is_root:
            return "Elevated: running as root"
        if self.pkexec_available:
            return "Standard user: privileged helper available"
        return "Standard user: privileged helper unavailable"

    @property
    def can_run_privileged_operations(self) -> bool:
        return self.is_root or self.pkexec_available


def detect_privileges() -> PrivilegeStatus:
    """Inspect available Linux capabilities without changing process state."""
    uid = os.geteuid()
    return PrivilegeStatus(
        mode=PrivilegeMode.ROOT if uid == 0 else PrivilegeMode.USER,
        effective_uid=uid,
        is_root=uid == 0,
        pkexec_available=shutil.which("pkexec") is not None,
        nft_available=shutil.which("nft") is not None,
        ip_available=shutil.which("ip") is not None,
        network_manager_available=shutil.which("nmcli") is not None,
    )
