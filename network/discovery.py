"""Cross-platform local-network discovery.

NetFather combines the operating system neighbour/ARP cache (passive) with an
optional Scapy ARP sweep (active).  Active discovery is limited to the local
IPv4 subnet and falls back to passive discovery when Scapy, capture drivers or
privileges are unavailable.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass

from core.logger import get_logger
from core.platform import PlatformFamily, platform_family
from network.device import lookup_vendor
from network.interface import get_network_status

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
    """Normalized discovery record from either active or passive backends."""

    ip: str
    interface: str | None = None
    mac: str | None = None
    state: str | None = None
    vendor: str | None = None
    hostname: str | None = None
    device_type: str | None = None
    os_hint: str | None = None
    source: str = "passive"


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
    """Deduplicate exact IP/interface rows; the newest row wins.

    This preserves passive neighbour-cache semantics: the same IP observed on
    two interfaces is two records, while a later state for the same
    IP/interface replaces the earlier one.
    """
    by_identity: dict[tuple[str, str | None], DiscoveredHost] = {}
    for host in hosts:
        by_identity[(host.ip, host.interface)] = host
    return list(by_identity.values())


def _merge_discovery(hosts: list[DiscoveredHost]) -> list[DiscoveredHost]:
    """Merge active/passive observations by MAC when that is unambiguous."""
    result: list[DiscoveredHost] = []
    mac_index: dict[str, int] = {}
    identity_index: dict[tuple[str, str | None], int] = {}
    for host in hosts:
        index: int | None = None
        if host.mac:
            index = mac_index.get(host.mac.lower())
        if index is None:
            index = identity_index.get((host.ip, host.interface))
        if index is None:
            result.append(host)
            index = len(result) - 1
            if host.mac:
                mac_index[host.mac.lower()] = index
            identity_index[(host.ip, host.interface)] = index
            continue
        current = result[index]
        for attr in ("interface", "mac", "state", "vendor", "hostname", "device_type", "os_hint"):
            value = getattr(host, attr)
            if value and (not getattr(current, attr) or host.source == "active"):
                setattr(current, attr, value)
        if host.source == "active" and current.source == "passive":
            current.source = "active+passive"
    return result


def _enrich_vendors(hosts: list[DiscoveredHost], enabled: bool = True) -> list[DiscoveredHost]:
    if not enabled:
        return hosts
    for host in hosts:
        if host.mac and not host.vendor:
            host.vendor = lookup_vendor(host.mac)
    return hosts


def _resolve_hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, socket.herror, socket.gaierror):
        return None


def _guess_device_type(host: DiscoveredHost) -> str:
    text = " ".join(filter(None, (host.hostname, host.vendor))).lower()
    if any(x in text for x in ("iphone", "android", "pixel", "samsung", "xiaomi", "huawei")):
        return "phone"
    if any(x in text for x in ("ipad", "tablet")):
        return "tablet"
    if any(x in text for x in ("printer", "epson", "brother", "canon")):
        return "printer"
    if any(x in text for x in ("router", "gateway", "mikrotik", "ubiquiti", "tp-link", "cisco")):
        return "router"
    if any(x in text for x in ("tv", "roku", "chromecast", "appletv")):
        return "media"
    if any(x in text for x in ("camera", "esp", "tuya", "sonoff", "iot")):
        return "iot"
    if host.hostname:
        return "computer"
    return "unknown"


def _guess_os_from_ttl(ttl: int | None) -> str | None:
    if ttl is None:
        return None
    if ttl <= 64:
        return "Unix/Linux/macOS-like"
    if ttl <= 128:
        return "Windows-like"
    return "network/embedded"


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
# Active discovery: Scapy ARP + optional ICMP TTL hint
# ---------------------------------------------------------------------------


def infer_local_subnet(platform_name: str | None = None) -> str | None:
    status = get_network_status(platform_name)
    if not status.local_ip:
        return None
    prefix = status.prefix_length
    if prefix is None and status.netmask:
        try:
            prefix = ipaddress.ip_network(f"0.0.0.0/{status.netmask}").prefixlen
        except ValueError:
            prefix = None
    # A conservative /24 fallback keeps active probing inside the common LAN
    # segment rather than scanning a huge guessed network.
    prefix = 24 if prefix is None else max(16, min(30, int(prefix)))
    try:
        return str(ipaddress.ip_network(f"{status.local_ip}/{prefix}", strict=False))
    except ValueError:
        return None


def _scan_scapy(subnet: str, timeout_seconds: int) -> list[DiscoveredHost]:
    try:
        from scapy.all import ARP, Ether, srp  # type: ignore[import-not-found]
    except ImportError:
        log.info("Scapy kurulu değil; active discovery passive metoda düşüyor.")
        return []
    try:
        network = ipaddress.ip_network(subnet, strict=False)
        if network.version != 4:
            return []
        # Refuse unexpectedly broad ranges even if a config file is edited by
        # hand. Local active discovery should stay local and bounded.
        if network.prefixlen < 16:
            log.warning("Active discovery subnet çok geniş, tarama reddedildi: %s", subnet)
            return []
        answered, _ = srp(
            Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=str(network)),
            timeout=max(1, timeout_seconds),
            inter=0.01,
            retry=0,
            verbose=False,
        )
    except (OSError, PermissionError, RuntimeError, ValueError) as exc:
        log.info("Scapy active discovery kullanılamadı: %s", exc)
        return []
    except Exception as exc:  # Scapy/Npcap backend failures vary by OS
        log.info("Scapy active discovery başarısız, passive fallback kullanılacak: %s", exc)
        return []

    hosts: list[DiscoveredHost] = []
    for _sent, received in answered:
        ip_text = str(getattr(received, "psrc", "") or "")
        mac = _valid_mac_or_none(str(getattr(received, "hwsrc", "") or ""))
        if ip_text and not _is_meaningless_address(ip_text):
            hosts.append(
                DiscoveredHost(ip=ip_text, mac=mac, state="REACHABLE", source="active")
            )
    return _dedupe(hosts)


def _probe_os_hint(ip: str, timeout: float = 0.35) -> str | None:
    try:
        from scapy.all import ICMP, IP, sr1  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        response = sr1(IP(dst=ip) / ICMP(), timeout=timeout, verbose=False)
    except Exception:
        return None
    ttl = int(response.ttl) if response is not None and hasattr(response, "ttl") else None
    return _guess_os_from_ttl(ttl)


def _enrich_host_metadata(
    hosts: list[DiscoveredHost],
    *,
    hostname_resolution: bool,
    os_detection: bool,
) -> list[DiscoveredHost]:
    for index, host in enumerate(hosts):
        if hostname_resolution and not host.hostname:
            host.hostname = _resolve_hostname(host.ip)
        if os_detection and not host.os_hint and index < 64:
            host.os_hint = _probe_os_hint(host.ip)
        if not host.device_type:
            host.device_type = _guess_device_type(host)
    return hosts


def _scan_passive(timeout_seconds: int, family: PlatformFamily) -> list[DiscoveredHost]:
    if family is PlatformFamily.LINUX:
        return _scan_linux(timeout_seconds)
    if family is PlatformFamily.WINDOWS:
        return _scan_windows(timeout_seconds)
    if family is PlatformFamily.MACOS:
        return _scan_macos(timeout_seconds)
    raw = _run_arp_a(timeout_seconds)
    return _parse_windows_arp_output(raw) if raw else []


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------


def scan_network(
    timeout_seconds: int = _COMMAND_TIMEOUT_SECONDS_DEFAULT,
    platform_name: str | None = None,
    *,
    mode: str = "passive",
    subnet: str | None = None,
    hostname_resolution: bool = False,
    vendor_detection: bool = True,
    os_detection: bool = False,
    active_timeout_seconds: int | None = None,
) -> list[DiscoveredHost]:
    """Discover local IPv4 hosts using passive, active, or hybrid mode."""
    family = platform_family(platform_name)
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"passive", "active", "hybrid"}:
        normalized_mode = "passive"
    try:
        passive = (
            _scan_passive(timeout_seconds, family)
            if normalized_mode in {"passive", "hybrid"}
            else []
        )
        active: list[DiscoveredHost] = []
        if normalized_mode in {"active", "hybrid"}:
            cidr = subnet or infer_local_subnet(platform_name)
            if cidr:
                active = _scan_scapy(cidr, active_timeout_seconds or min(timeout_seconds, 5))
        hosts = _merge_discovery(passive + active)
        hosts = _enrich_vendors(hosts, vendor_detection)
        return _enrich_host_metadata(
            hosts,
            hostname_resolution=hostname_resolution,
            os_detection=os_detection,
        )
    except Exception as exc:  # discovery must not crash CLI/TUI
        log.warning("Discovery failed for %s: %s", family.value, exc)
        return []
