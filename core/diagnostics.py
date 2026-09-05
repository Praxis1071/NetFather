"""Read-only cross-platform installation/runtime diagnostics."""

from __future__ import annotations

import os
import shutil
import sys
import importlib.util
from dataclasses import dataclass
from pathlib import Path

from core.config import Config
from core.database import Database
from core.platform import PlatformFamily, get_platform_info
from network.device import find_oui_database
from network.interface import get_network_status
from firewall.backends import get_firewall_backend


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    ok: bool | None
    detail: str


def _writable_parent(path: Path) -> bool:
    parent = path.parent
    return parent.exists() and os.access(parent, os.W_OK)


def _network_tools_check() -> DiagnosticCheck:
    info = get_platform_info()
    if info.family is PlatformFamily.LINUX:
        path = shutil.which("ip")
        return DiagnosticCheck("Network backend", path is not None, path or "ip command not found")
    if info.family is PlatformFamily.WINDOWS:
        shell = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
        arp = shutil.which("arp")
        if shell:
            return DiagnosticCheck("Network backend", True, f"PowerShell: {shell}")
        return DiagnosticCheck(
            "Network backend",
            True if arp else False,
            f"PowerShell unavailable; arp fallback: {arp or 'not found'}",
        )
    if info.family is PlatformFamily.MACOS:
        route = shutil.which("route") or ("/sbin/route" if Path("/sbin/route").exists() else None)
        arp = shutil.which("arp") or ("/usr/sbin/arp" if Path("/usr/sbin/arp").exists() else None)
        ok = bool(route and arp)
        return DiagnosticCheck(
            "Network backend",
            ok,
            f"route={route or '-'} arp={arp or '-'}",
        )
    return DiagnosticCheck("Network backend", None, "unsupported OS; socket fallback only")




def _active_discovery_check() -> DiagnosticCheck:
    scapy = importlib.util.find_spec("scapy") is not None
    return DiagnosticCheck(
        "Active discovery", True if scapy else None,
        "Scapy available" if scapy else "Scapy unavailable; passive discovery remains usable",
    )

def _firewall_check(config: Config) -> DiagnosticCheck:
    backend = get_firewall_backend(config.firewall.backend)
    if backend.name == "nftables":
        tool = shutil.which("nft")
    elif backend.name == "windows":
        tool = shutil.which("powershell.exe") or shutil.which("pwsh")
    elif backend.name == "pf":
        tool = shutil.which("pfctl") or ("/sbin/pfctl" if Path("/sbin/pfctl").exists() else None)
    else:
        tool = None
    if tool:
        ok = True
    elif backend.name == "none" or not config.firewall.enforcement_enabled:
        ok = None
    else:
        ok = False
    mode = "enabled" if config.firewall.enforcement_enabled else "dry-run by default"
    return DiagnosticCheck("Firewall backend", ok, f"{backend.name}: {tool or 'tool unavailable'}; {mode}")

def run_diagnostics(config: Config, db: Database) -> list[DiagnosticCheck]:
    """Run non-destructive checks for common NetFather setup problems."""
    checks: list[DiagnosticCheck] = []
    info = get_platform_info()

    checks.append(
        DiagnosticCheck(
            "Platform",
            info.supported,
            f"{info.label}; backend={info.network_backend}",
        )
    )
    checks.append(
        DiagnosticCheck(
            "Python",
            sys.version_info >= (3, 12),
            sys.version.split()[0],
        )
    )
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
