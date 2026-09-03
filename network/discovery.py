"""Cross-platform passive local-network discovery.

The module reads the host operating system's neighbor/ARP cache; it does not
send active probes and never persists unknown devices automatically.

Backends:
- Linux: ``ip neigh``
- Windows: PowerShell ``Get-NetNeighbor`` with ``arp -a`` fallback
- macOS: ``arp -an``

All backends normalize into :class:`DiscoveredHost` and optionally enrich MAC
addresses using NetFather's local-only OUI lookup.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from core.logger import get_logger
from core.platform import PlatformFamily, platform_family
from network.device import lookup_vendor

log = get_logger("network.discovery")

_COMMAND_TIMEOUT_SECONDS_DEFAULT = 5


def _is_meaningless_address(ip_text: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return (
        ip_obj.is_loopback
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
        or ip_text == "255.255.255.255"
    )


@dataclass
class DiscoveredHost:
    """Normalized passive neighbor-cache record."""

    ip: str
    interface: str | None = None
    mac: str | None = None
    state: str | None = None
    vendor: str | None = None


def _normalize_discovery_mac(mac: str) -> str:
    return mac.strip().lower().replace("-", ":")


def _valid_mac_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = _normalize_discovery_mac(value)
    if re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", candidate):
        if candidate != "00:00:00:00:00:00":
            return candidate
    return None


def _dedupe(hosts: list[DiscoveredHost]) -> list[DiscoveredHost]:
    by_identity: dict[tuple[str, str | None], DiscoveredHost] = {}
    for host in hosts:
        by_identity[(host.ip, host.interface)] = host
    return list(by_identity.values())


def _enrich_vendors(hosts: list[DiscoveredHost]) -> list[DiscoveredHost]:
    for host in hosts:
        if host.mac and not host.vendor:
            host.vendor = lookup_vendor(host.mac)
    return hosts


def _run_process(args: list[str], timeout_seconds: int) -> str | None:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.debug("Discovery command failed (%s): %s", args[0] if args else "?", exc)
        return None
    if result.returncode != 0:
        log.debug(
            "Discovery command returned %s (%s): %s",
            result.returncode,
            args[0] if args else "?",
            result.stderr.strip(),
        )
        return None
    return result.stdout


# ---------------------------------------------------------------------------
# Linux: ip neigh
# ---------------------------------------------------------------------------


def _parse_neigh_line(line: str) -> DiscoveredHost | None:
    tokens = line.split()
    if len(tokens) < 3 or tokens[1] != "dev":
        return None

    ip_text = tokens[0]
    interface = tokens[2]
    if _is_meaningless_address(ip_text):
        return None

    remaining = tokens[3:]
    mac: str | None = None
    if len(remaining) >= 2 and remaining[0] == "lladdr":
        mac = _valid_mac_or_none(remaining[1])
        remaining = remaining[2:]

    state = remaining[-1] if remaining else None
    return DiscoveredHost(ip=ip_text, interface=interface, mac=mac, state=state)


def _parse_ip_neigh_output(raw_output: str) -> list[DiscoveredHost]:
    hosts: list[DiscoveredHost] = []
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        host = _parse_neigh_line(line)
        if host is not None:
            hosts.append(host)
        else:
            log.debug("Skipping unparseable ip-neigh line: %r", line)
    return _dedupe(hosts)


def _run_ip_neigh(timeout_seconds: int) -> str | None:
    ip_binary = shutil.which("ip")
    if ip_binary is None:
        return None
    return _run_process([ip_binary, "neigh"], timeout_seconds)


def _scan_linux(timeout_seconds: int) -> list[DiscoveredHost]:
    raw = _run_ip_neigh(timeout_seconds)
    return _parse_ip_neigh_output(raw) if raw else []


# ---------------------------------------------------------------------------
# Windows: Get-NetNeighbor + arp -a fallback
# ---------------------------------------------------------------------------

_WINDOWS_NEIGHBOR_PS = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'SilentlyContinue'
Get-NetNeighbor -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -and $_.State -ne 'Unreachable' } |
    Select-Object IPAddress, LinkLayerAddress, State, InterfaceAlias |
    ConvertTo-Json -Compress
""".strip()


def _find_powershell() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")


def _run_windows_neighbors(timeout_seconds: int) -> str | None:
    shell = _find_powershell()
    if shell is None:
        return None
    return _run_process(
        [shell, "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_NEIGHBOR_PS],
        timeout_seconds,
    )


def _parse_windows_neighbors_json(raw_output: str) -> list[DiscoveredHost]:
    try:
        payload = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return []
    rows = payload if isinstance(payload, list) else [payload]
    hosts: list[DiscoveredHost] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ip_text = str(row.get("IPAddress") or "").strip()
        if not ip_text or _is_meaningless_address(ip_text):
            continue
        hosts.append(
            DiscoveredHost(
                ip=ip_text,
                interface=str(row.get("InterfaceAlias") or "").strip() or None,
                mac=_valid_mac_or_none(row.get("LinkLayerAddress")),
                state=str(row.get("State") or "").strip() or None,
            )
        )
    return _dedupe(hosts)

_WINDOWS_ARP_INTERFACE_RE = re.compile(r"^\s*Interface:\s+(?P<interface>\S+)", re.I)
_WINDOWS_ARP_ROW_RE = re.compile(
    r"^\s*(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(?P<mac>[0-9A-Fa-f-]{17})\s+(?P<state>\S+)\s*$"
)


def _parse_windows_arp_output(raw_output: str) -> list[DiscoveredHost]:
    interface: str | None = None
    hosts: list[DiscoveredHost] = []
    for line in raw_output.splitlines():
        interface_match = _WINDOWS_ARP_INTERFACE_RE.match(line)
        if interface_match:
            interface = interface_match.group("interface")
            continue
        match = _WINDOWS_ARP_ROW_RE.match(line)
        if not match:
            continue
        ip_text = match.group("ip")
        if _is_meaningless_address(ip_text):
            continue
        hosts.append(
            DiscoveredHost(
                ip=ip_text,
                interface=interface,
                mac=_valid_mac_or_none(match.group("mac")),
                state=match.group("state").upper(),
            )
        )
    return _dedupe(hosts)


def _run_arp_a(timeout_seconds: int) -> str | None:
    arp = shutil.which("arp")
    if arp is None:
        return None
    return _run_process([arp, "-a"], timeout_seconds)


def _scan_windows(timeout_seconds: int) -> list[DiscoveredHost]:
    raw = _run_windows_neighbors(timeout_seconds)
    if raw:
        hosts = _parse_windows_neighbors_json(raw)
        if hosts:
            return hosts
    raw = _run_arp_a(timeout_seconds)
    return _parse_windows_arp_output(raw) if raw else []


# ---------------------------------------------------------------------------
# macOS: arp -an
# ---------------------------------------------------------------------------

_MACOS_ARP_RE = re.compile(
    r"^\?\s+\((?P<ip>[^)]+)\)\s+at\s+(?P<mac>\S+)\s+on\s+(?P<interface>\S+)(?P<rest>.*)$"
)


def _parse_macos_arp_output(raw_output: str) -> list[DiscoveredHost]:
    hosts: list[DiscoveredHost] = []
    for line in raw_output.splitlines():
        match = _MACOS_ARP_RE.match(line.strip())
        if not match:
            continue
        ip_text = match.group("ip")
        if _is_meaningless_address(ip_text):
            continue
        mac_token = match.group("mac")
        incomplete = mac_token.lower() in {"(incomplete)", "incomplete"}
        hosts.append(
            DiscoveredHost(
                ip=ip_text,
                interface=match.group("interface"),
                mac=None if incomplete else _valid_mac_or_none(mac_token),
                state="INCOMPLETE" if incomplete else "REACHABLE",
            )
        )
    return _dedupe(hosts)


def _run_macos_arp(timeout_seconds: int) -> str | None:
    arp = shutil.which("arp") or "/usr/sbin/arp"
    return _run_process([arp, "-an"], timeout_seconds)


def _scan_macos(timeout_seconds: int) -> list[DiscoveredHost]:
    raw = _run_macos_arp(timeout_seconds)
    return _parse_macos_arp_output(raw) if raw else []


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------


def scan_network(
    timeout_seconds: int = _COMMAND_TIMEOUT_SECONDS_DEFAULT,
    platform_name: str | None = None,
) -> list[DiscoveredHost]:
    """Read the local neighbor cache for the current operating system."""
    family = platform_family(platform_name)
    try:
        if family is PlatformFamily.LINUX:
            hosts = _scan_linux(timeout_seconds)
        elif family is PlatformFamily.WINDOWS:
            hosts = _scan_windows(timeout_seconds)
        elif family is PlatformFamily.MACOS:
            hosts = _scan_macos(timeout_seconds)
        else:
            raw = _run_arp_a(timeout_seconds)
            hosts = _parse_windows_arp_output(raw) if raw else []
        return _enrich_vendors(hosts)
    except Exception as exc:  # noqa: BLE001 - discovery must not crash CLI/TUI
        log.warning("Discovery failed for %s: %s", family.value, exc)
        return []
