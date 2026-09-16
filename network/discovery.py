"""Linux local-network discovery using iproute2, Scapy and optional Nmap."""
from __future__ import annotations

import ipaddress
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass, field

from core.logger import get_logger
from network.device import lookup_vendor
from network.identity import DeviceObservation
from network.interface import get_network_status

log = get_logger("network.discovery")
_COMMAND_TIMEOUT_SECONDS_DEFAULT = 5


@dataclass
class DiscoveredHost:
    ip: str
    interface: str | None = None
    mac: str | None = None
    state: str | None = None
    vendor: str | None = None
    hostname: str | None = None
    device_type: str | None = None
    os_hint: str | None = None
    source: str = "passive"
    open_tcp_ports: tuple[int, ...] = field(default_factory=tuple)
    open_udp_ports: tuple[int, ...] = field(default_factory=tuple)
    services: tuple[str, ...] = field(default_factory=tuple)
    scan_method: str | None = None
    latency_ms: float | None = None


def _is_meaningless_address(ip_text: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return ip_obj.is_loopback or ip_obj.is_multicast or ip_obj.is_unspecified or ip_text == "255.255.255.255"


def _valid_mac_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower().replace("-", ":")
    if re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", candidate) and candidate != "00:00:00:00:00:00":
        return candidate
    return None


def _dedupe(hosts: list[DiscoveredHost]) -> list[DiscoveredHost]:
    by_identity: dict[tuple[str, str | None], DiscoveredHost] = {}
    for host in hosts:
        by_identity[(host.ip, host.interface)] = host
    return list(by_identity.values())


def _merge_discovery(hosts: list[DiscoveredHost]) -> list[DiscoveredHost]:
    result: list[DiscoveredHost] = []
    mac_index: dict[str, int] = {}
    identity_index: dict[tuple[str, str | None], int] = {}
    for host in hosts:
        index = mac_index.get(host.mac.lower()) if host.mac else None
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
            if value and (not getattr(current, attr) or host.source in {"active", "deep", "active+passive"}):
                setattr(current, attr, value)
        if host.open_tcp_ports:
            current.open_tcp_ports = tuple(sorted(set(current.open_tcp_ports) | set(host.open_tcp_ports)))
        if host.open_udp_ports:
            current.open_udp_ports = tuple(sorted(set(current.open_udp_ports) | set(host.open_udp_ports)))
        if host.services:
            current.services = tuple(dict.fromkeys((*current.services, *host.services)))
        if host.latency_ms is not None:
            current.latency_ms = host.latency_ms
        if host.scan_method:
            current.scan_method = host.scan_method
        if host.source == "active" and current.source == "passive":
            current.source = "active+passive"
        elif host.source == "deep":
            current.source = "deep+" + current.source if current.source != "passive" else "deep"
    return result


def _run_process(args: list[str], timeout_seconds: int) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_seconds, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.debug("Discovery command failed: %s", exc)
        return None
    return result.stdout if result.returncode == 0 else None


def _parse_ip_neigh_output(raw_output: str) -> list[DiscoveredHost]:
    hosts: list[DiscoveredHost] = []
    for line in raw_output.splitlines():
        tokens = line.split()
        if len(tokens) < 3 or tokens[1] != "dev":
            continue
        ip_text, interface = tokens[0], tokens[2]
        if _is_meaningless_address(ip_text):
            continue
        remaining = tokens[3:]
        mac = _valid_mac_or_none(remaining[1]) if len(remaining) >= 2 and remaining[0] == "lladdr" else None
        state_tokens = remaining[2:] if mac else remaining
        hosts.append(DiscoveredHost(ip=ip_text, interface=interface, mac=mac, state=state_tokens[-1] if state_tokens else None))
    return _dedupe(hosts)


def _scan_linux(timeout_seconds: int) -> list[DiscoveredHost]:
    ip_binary = shutil.which("ip")
    if ip_binary is None:
        return []
    raw = _run_process([ip_binary, "neigh"], timeout_seconds)
    return _parse_ip_neigh_output(raw) if raw else []


def infer_local_subnet() -> str | None:
    status = get_network_status()
    if not status.local_ip:
        return None
    prefix = status.prefix_length or 24
    prefix = max(16, min(30, int(prefix)))
    try:
        return str(ipaddress.ip_network(f"{status.local_ip}/{prefix}", strict=False))
    except ValueError:
        return None


def _scan_scapy(subnet: str, timeout_seconds: int) -> list[DiscoveredHost]:
    try:
        from scapy.all import ARP, Ether, srp  # type: ignore[import-not-found]
        network = ipaddress.ip_network(subnet, strict=False)
        if network.version != 4 or network.prefixlen < 16:
            return []
        answered, _ = srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=str(network)), timeout=max(1, timeout_seconds), inter=0.01, retry=0, verbose=False)
    except ImportError:
        log.info("Scapy is not installed; active discovery unavailable.")
        return []
    except Exception as exc:
        log.info("Scapy active discovery unavailable: %s", exc)
        return []
    hosts: list[DiscoveredHost] = []
    for _sent, received in answered:
        ip_text = str(getattr(received, "psrc", "") or "")
        mac = _valid_mac_or_none(str(getattr(received, "hwsrc", "") or ""))
        if ip_text and not _is_meaningless_address(ip_text):
            hosts.append(DiscoveredHost(ip=ip_text, mac=mac, state="REACHABLE", source="active", scan_method="scapy-arp"))
    return _dedupe(hosts)


def _resolve_hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, socket.herror, socket.gaierror):
        return None


def _guess_device_type(host: DiscoveredHost) -> str:
    text = " ".join(filter(None, (host.hostname, host.vendor, host.device_type, host.os_hint))).lower()
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
    return "computer" if host.hostname else "unknown"


def _guess_os_from_ttl(ttl: int | None) -> str | None:
    if ttl is None:
        return None
    if ttl <= 64:
        return "Linux/Unix-like"
    if ttl <= 128:
        return "Windows-like"
    return "network/embedded"


def _probe_os_hint(ip: str, timeout: float = 0.35) -> str | None:
    try:
        from scapy.all import ICMP, IP, sr1  # type: ignore[import-not-found]
        response = sr1(IP(dst=ip) / ICMP(), timeout=timeout, verbose=False)
        ttl = int(response.ttl) if response is not None and hasattr(response, "ttl") else None
        return _guess_os_from_ttl(ttl)
    except Exception:
        return None


def _apply_deep_scan(hosts: list[DiscoveredHost], subnet: str) -> tuple[list[DiscoveredHost], tuple[str, ...]]:
    try:
        from network.deep_scan import run_deep_scan
        report = run_deep_scan(subnet, include_udp=True, include_os=True, include_versions=True)
    except ValueError as exc:
        return hosts, (str(exc),)
    except Exception as exc:
        log.warning("Deep scan failed: %s", exc)
        return hosts, (f"Deep scan failed: {exc}",)
    by_ip = {host.ip: host for host in hosts}
    for result in report.hosts:
        host = by_ip.get(result.ip)
        if host is None:
            host = DiscoveredHost(ip=result.ip, source="deep")
            hosts.append(host)
            by_ip[result.ip] = host
        host.mac = _valid_mac_or_none(result.mac) or host.mac
        host.vendor = result.vendor or host.vendor
        host.hostname = result.hostname or host.hostname
        host.os_hint = result.os_name or host.os_hint
        host.device_type = result.device_type or host.device_type
        host.open_tcp_ports = result.open_tcp_ports
        host.open_udp_ports = result.open_udp_ports
        host.services = result.services
        host.scan_method = "nmap"
        host.latency_ms = result.latency_ms
        host.state = "REACHABLE"
    return hosts, report.warnings


def _enrich(hosts: list[DiscoveredHost], *, hostname_resolution: bool, vendor_detection: bool, os_detection: bool) -> list[DiscoveredHost]:
    for host in hosts:
        if vendor_detection and host.mac and not host.vendor:
            host.vendor = lookup_vendor(host.mac)
        if hostname_resolution and not host.hostname:
            host.hostname = _resolve_hostname(host.ip)
        if os_detection and not host.os_hint:
            host.os_hint = _probe_os_hint(host.ip)
        if not host.device_type:
            host.device_type = _guess_device_type(host)
    return hosts


def observations_from_hosts(hosts: list[DiscoveredHost]) -> list[DeviceObservation]:
    """Convert discovery records into identity observations with source confidence."""
    observations: list[DeviceObservation] = []
    for host in hosts:
        if not host.mac:
            continue
        source = host.source.strip().lower() or "unknown"
        confidence = 0.95 if "active" in source else 0.8
        if "deep" in source:
            confidence = min(1.0, confidence + 0.03)
        if host.hostname:
            confidence = min(1.0, confidence + 0.03)
        if host.vendor:
            confidence = min(1.0, confidence + 0.02)
        observations.append(DeviceObservation(mac=host.mac, ip=host.ip, hostname=host.hostname, vendor=host.vendor, interface=host.interface, device_type=host.device_type, os_hint=host.os_hint, source=source, confidence=confidence))
    return observations


def scan_network(timeout_seconds: int = _COMMAND_TIMEOUT_SECONDS_DEFAULT, *, mode: str = "passive", subnet: str | None = None, hostname_resolution: bool = False, vendor_detection: bool = True, os_detection: bool = False, active_timeout_seconds: int | None = None) -> list[DiscoveredHost]:
    """Discover local IPv4 hosts using layered Linux discovery and optional deep Nmap inventory."""
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"passive", "active", "hybrid", "deep"}:
        normalized_mode = "passive"
    try:
        passive = _scan_linux(timeout_seconds) if normalized_mode in {"passive", "hybrid", "deep"} else []
        active = []
        if normalized_mode in {"active", "hybrid", "deep"}:
            cidr = subnet or infer_local_subnet()
            if cidr:
                active = _scan_scapy(cidr, active_timeout_seconds or min(timeout_seconds, 5))
        hosts = _merge_discovery(passive + active)
        if normalized_mode == "deep":
            cidr = subnet or infer_local_subnet()
            if cidr:
                hosts, warnings = _apply_deep_scan(hosts, cidr)
                for warning in warnings:
                    log.warning("%s", warning)
        return _enrich(hosts, hostname_resolution=hostname_resolution, vendor_detection=vendor_detection, os_detection=os_detection)
    except Exception as exc:
        log.warning("Linux discovery failed: %s", exc)
        return []
