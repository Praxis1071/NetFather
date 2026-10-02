"""Linux network interface, local IP and gateway detection."""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
from dataclasses import dataclass

from core.logger import get_logger

log = get_logger("network.interface")
_ROUTE_PROBE_TARGET = "8.8.8.8"
_COMMAND_TIMEOUT_SECONDS = 3
_ROUTE_GET_PATTERN = re.compile(
    r"(?:via\s+(?P<gateway>\S+)\s+)?dev\s+(?P<interface>\S+)"
    r"(?:.*?\bsrc\s+(?P<src_ip>\S+))?"
)


@dataclass
class NetworkStatus:
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
        log.debug("Linux network command failed (%s): %s", args[0] if args else "?", exc)
        return None
    return result.stdout if result.returncode == 0 else None


def _parse_route_get_output(raw: str) -> NetworkStatus:
    """Parse the stable fields from ``ip route get`` output."""
    status = NetworkStatus()
    match = _ROUTE_GET_PATTERN.search(raw)
    if match:
        status.interface = match.group("interface")
        status.gateway = match.group("gateway")
        status.local_ip = match.group("src_ip")
    return status


def _socket_local_ip(target: str = _ROUTE_PROBE_TARGET) -> str | None:
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


def _linux_network_status() -> NetworkStatus:
    ip_binary = shutil.which("ip")
    if ip_binary is None:
        return NetworkStatus(local_ip=_socket_local_ip())

    raw = _run_process([ip_binary, "route", "get", _ROUTE_PROBE_TARGET])
    status = _parse_route_get_output(raw) if raw else NetworkStatus()

    if status.interface:
        addr = _run_process([ip_binary, "-o", "-4", "addr", "show", "dev", status.interface])
        if addr:
            match = re.search(r"\binet\s+(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})", addr)
            if match:
                status.local_ip = status.local_ip or match.group(1)
                status.prefix_length = int(match.group(2))

    status.local_ip = status.local_ip or _socket_local_ip()
    return status


def get_local_ipv4_addresses() -> set[str]:
    """Return all configured global IPv4 addresses on the host."""
    ip_binary = shutil.which("ip")
    if ip_binary is None:
        status = get_network_status()
        return {status.local_ip} if status.local_ip else set()
    raw = _run_process([ip_binary, "-o", "-4", "addr", "show", "scope", "global"])
    if not raw:
        status = get_network_status()
        return {status.local_ip} if status.local_ip else set()
    addresses: set[str] = set()
    for line in raw.splitlines():
        match = re.search(r"\binet\s+(\d{1,3}(?:\.\d{1,3}){3})/", line)
        if match:
            addresses.add(match.group(1))
    return addresses


def get_network_status() -> NetworkStatus:
    """Return the current Linux IPv4 interface, address and gateway."""
    try:
        return _linux_network_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("Linux network status detection failed: %s", exc)
        return NetworkStatus(local_ip=_socket_local_ip())
