"""Read-only installation/runtime diagnostics used by ``netfather doctor``."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from core.config import Config
from core.database import Database
from network.device import find_oui_database
from network.interface import get_network_status


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    ok: bool | None
    detail: str


def _writable_parent(path: Path) -> bool:
    parent = path.parent
    return parent.exists() and os.access(parent, os.W_OK | os.X_OK)


def run_diagnostics(config: Config, db: Database) -> list[DiagnosticCheck]:
    """Run non-destructive checks for common NetFather setup problems."""
    checks: list[DiagnosticCheck] = []

    linux = sys.platform.startswith("linux")
    checks.append(
        DiagnosticCheck(
            "Platform",
            linux,
            sys.platform if linux else f"{sys.platform} (Linux is the supported target)",
        )
    )

    ip_binary = shutil.which("ip")
    checks.append(
        DiagnosticCheck("ip command", ip_binary is not None, ip_binary or "not found in PATH")
    )

    net = get_network_status()
    network_known = any((net.interface, net.local_ip, net.gateway))
    checks.append(
        DiagnosticCheck(
            "Network route",
            True if network_known else None,
            (
                f"interface={net.interface or '-'} ip={net.local_ip or '-'} gateway={net.gateway or '-'}"
                if network_known
                else "no active/default route detected"
            ),
        )
    )

    checks.append(
        DiagnosticCheck(
            "Config",
            config.config_path.is_file() and os.access(config.config_path, os.R_OK),
            str(config.config_path),
        )
    )
    checks.append(
        DiagnosticCheck(
            "Database",
            db.db_path.exists() and _writable_parent(db.db_path),
            str(db.db_path),
        )
    )

    oui = find_oui_database()
    checks.append(
        DiagnosticCheck(
            "Local OUI database",
            True if oui else None,
            str(oui) if oui else "not installed; vendor names will be unavailable",
        )
    )
    return checks
