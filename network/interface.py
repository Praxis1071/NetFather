"""Cross-platform active network interface, local IP and gateway detection.

Linux uses ``ip route get``; Windows uses PowerShell's ``Get-NetIPConfiguration``;
macOS uses ``route -n get default`` + ``ipconfig getifaddr``.  A UDP socket probe
provides a safe local-IP fallback on unknown/minimal systems.  Parsers are kept
separate from command execution so they can be tested without touching the host.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass

from core.logger import get_logger
from core.platform import PlatformFamily, platform_family

log = get_logger("network.interface")

_ROUTE_PROBE_TARGET = "8.8.8.8"
_COMMAND_TIMEOUT_SECONDS = 3

_ROUTE_GET_PATTERN = re.compile(
    r"(?:via\s+(?P<gateway>\S+)\s+)?dev\s+(?P<interface>\S+)"
    r"(?:.*?\bsrc\s+(?P<src_ip>\S+))?"
)
_MACOS_ROUTE_FIELD = re.compile(r"^\s*(?P<key>gateway|interface):\s*(?P<value>\S+)\s*$", re.M)


@dataclass
class NetworkStatus:
    """Normalized active network information."""

    interface: str | None = None
    local_ip: str | None = None
    gateway: str | None = None
    netmask: str | None = None
    prefix_length: int | None = None


def _run_process(args: list[str], timeout: int = _COMMAND_TIMEOUT_SECONDS) -> str | None:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.debug("Network command failed (%s): %s", args[0] if args else "?", exc)
        return None
    if result.returncode != 0:
        log.debug(
            "Network command returned %s (%s): %s",
            result.returncode,
            args[0] if args else "?",
            result.stderr.strip(),
        )
        return None
    return result.stdout


def _socket_local_ip(target: str = _ROUTE_PROBE_TARGET) -> str | None:
    """Return the outbound IPv4 address without sending application data."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(1.0)
        sock.connect((target, 80))
        value = sock.getsockname()[0]
        return value if value and value != "0.0.0.0" else None
    except OSError:
        return None
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# Linux backend
# ---------------------------------------------------------------------------


def _run_ip_route_get(target: str = _ROUTE_PROBE_TARGET) -> str | None:
    ip_binary = shutil.which("ip")
    if ip_binary is None:
        log.debug("'ip' command not found; Linux route detection is unavailable.")
        return None
    return _run_process([ip_binary, "route", "get", target])


def _parse_route_get_output(raw_output: str) -> NetworkStatus:
    match = _ROUTE_GET_PATTERN.search(raw_output)
    if match is None:
        return NetworkStatus()
    return NetworkStatus(
        interface=match.group("interface"),
        local_ip=match.group("src_ip"),
        gateway=match.group("gateway"),
    )


def _run_linux_addr(interface: str) -> str | None:
    ip_binary = shutil.which("ip")
    if ip_binary is None:
        return None
    return _run_process([ip_binary, "-o", "-4", "addr", "show", "dev", interface])


def _linux_network_status() -> NetworkStatus:
    raw = _run_ip_route_get()
    status = _parse_route_get_output(raw) if raw else NetworkStatus()
    if status.interface:
        addr = _run_linux_addr(status.interface)
        if addr:
            match = re.search(r"\binet\s+(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})", addr)
            if match:
                status.local_ip = status.local_ip or match.group(1)
                status.prefix_length = int(match.group(2))
    return status


# ---------------------------------------------------------------------------
# Windows backend
# ---------------------------------------------------------------------------

_WINDOWS_STATUS_PS = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'SilentlyContinue'
$c = Get-NetIPConfiguration | Where-Object {
    $_.IPv4DefaultGateway -and $_.IPv4Address
} | Select-Object -First 1
if ($null -ne $c) {
    [PSCustomObject]@{
        Interface = $c.InterfaceAlias
        IP = @($c.IPv4Address)[0].IPAddress
        Gateway = @($c.IPv4DefaultGateway)[0].NextHop
        PrefixLength = @($c.IPv4Address)[0].PrefixLength
    } | ConvertTo-Json -Compress
}
""".strip()


def _find_powershell() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")


def _run_windows_network_config() -> str | None:
    shell = _find_powershell()
    if shell is None:
        return None
    return _run_process([shell, "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_STATUS_PS])


def _parse_windows_network_json(raw_output: str) -> NetworkStatus:
    try:
        payload = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return NetworkStatus()
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        return NetworkStatus()
    prefix = payload.get("PrefixLength")
    try:
        prefix_value = int(prefix) if prefix is not None else None
    except (TypeError, ValueError):
        prefix_value = None
    return NetworkStatus(
        interface=str(payload.get("Interface") or "") or None,
        local_ip=str(payload.get("IP") or "") or None,
        gateway=str(payload.get("Gateway") or "") or None,
        prefix_length=prefix_value,
    )


def _windows_network_status() -> NetworkStatus:
    raw = _run_windows_network_config()
    status = _parse_windows_network_json(raw) if raw else NetworkStatus()
    if status.local_ip is None:
        status.local_ip = _socket_local_ip()
    return status


# ---------------------------------------------------------------------------
# macOS backend
# ---------------------------------------------------------------------------


def _run_macos_route_get() -> str | None:
    route = shutil.which("route") or "/sbin/route"
    return _run_process([route, "-n", "get", "default"])


def _parse_macos_route_get_output(raw_output: str) -> NetworkStatus:
    values = {m.group("key"): m.group("value") for m in _MACOS_ROUTE_FIELD.finditer(raw_output)}
    return NetworkStatus(interface=values.get("interface"), gateway=values.get("gateway"))


def _run_macos_ipconfig(interface: str) -> str | None:
    ipconfig = shutil.which("ipconfig") or "/usr/sbin/ipconfig"
    raw = _run_process([ipconfig, "getifaddr", interface])
    return raw.strip() if raw and raw.strip() else None


def _run_macos_netmask(interface: str) -> str | None:
    ipconfig = shutil.which("ipconfig") or "/usr/sbin/ipconfig"
    raw = _run_process([ipconfig, "getoption", interface, "subnet_mask"])
    return raw.strip() if raw and raw.strip() else None


def _macos_network_status() -> NetworkStatus:
    raw = _run_macos_route_get()
    status = _parse_macos_route_get_output(raw) if raw else NetworkStatus()
    if status.interface:
        status.local_ip = _run_macos_ipconfig(status.interface)
        status.netmask = _run_macos_netmask(status.interface)
        if status.netmask:
            try:
                import ipaddress
                status.prefix_length = ipaddress.ip_network(f"0.0.0.0/{status.netmask}").prefixlen
            except ValueError:
                pass
    if status.local_ip is None:
        status.local_ip = _socket_local_ip()
    return status


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------


def get_network_status(platform_name: str | None = None) -> NetworkStatus:
    """Return normalized network status for Linux, Windows or macOS.

    ``platform_name`` exists for deterministic tests and internal diagnostics;
    normal callers should omit it.
    """
    family = platform_family(platform_name)
    try:
        if family is PlatformFamily.LINUX:
            return _linux_network_status()
        if family is PlatformFamily.WINDOWS:
            return _windows_network_status()
        if family is PlatformFamily.MACOS:
            return _macos_network_status()
        return NetworkStatus(local_ip=_socket_local_ip())
    except Exception as exc:  # noqa: BLE001 - status must never take down CLI/TUI
        log.warning("Network status detection failed for %s: %s", family.value, exc)
        return NetworkStatus(local_ip=_socket_local_ip())
