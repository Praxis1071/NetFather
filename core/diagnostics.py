"""Read-only Linux installation/runtime diagnostics."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass

from core.config import Config
from core.database import Database
from core.platform import get_platform_info
from firewall.backends import get_firewall_backend
from network.device import find_oui_database
from network.interface import get_network_status


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    ok: bool | None
    detail: str


def _network_tools_check() -> DiagnosticCheck:
    info = get_platform_info()
    path = shutil.which("ip")
    if info["family"] != "linux":
        return DiagnosticCheck("Network backend", False, f"unsupported platform: {info['system']}")
    return DiagnosticCheck("Network backend", path is not None, path or "ip command not found")


def _active_discovery_check() -> DiagnosticCheck:
    scapy = importlib.util.find_spec("scapy") is not None
    return DiagnosticCheck(
        "Active discovery",
        True if scapy else None,
        "Scapy available" if scapy else "Scapy unavailable; passive discovery remains usable",
    )


def _firewall_check(config: Config) -> DiagnosticCheck:
    backend = get_firewall_backend(config.firewall.backend)
    tool = shutil.which("nft") if backend.name == "nftables" else None
    if tool:
        ok = True
    elif backend.name == "none" or not config.firewall.enforcement_enabled:
        ok = None
    else:
        ok = False
    mode = "enabled" if config.firewall.enforcement_enabled else "disabled by default"
    return DiagnosticCheck("Firewall backend", ok, f"{backend.name}: {tool or 'tool unavailable'}; {mode}")


def run_diagnostics(config: Config, db: Database) -> list[DiagnosticCheck]:
    """Run non-destructive checks for common Linux NetFather setup problems."""
    checks: list[DiagnosticCheck] = []
    info = get_platform_info()

    checks.append(
        DiagnosticCheck(
            "Platform",
            info["family"] == "linux",
            f"{info['system']} {info['release']}; backend={info['network_backend']}",
        )
    )
    checks.append(DiagnosticCheck("Python", sys.version_info >= (3, 12), sys.version.split()[0]))
    checks.append(_network_tools_check())
    checks.append(_active_discovery_check())
    checks.append(_firewall_check(config))

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
            db.db_path.exists() and os.access(db.db_path.parent, os.W_OK),
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
