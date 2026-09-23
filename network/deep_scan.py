"""Optional deep local-network inventory using the system Nmap binary.

The normal discovery path stays lightweight. This module adds a deliberately
opt-in, local-network-only deep pass for TCP/UDP services, service versions,
and OS fingerprinting when Nmap and the required Linux privileges are
available. Elevation is scoped to the Nmap process through pkexec; the GTK
application itself never needs to run as root.
"""
from __future__ import annotations

import ipaddress
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from core.logger import get_logger

log = get_logger("network.deep_scan")


@dataclass(frozen=True, slots=True)
class DeepScanResult:
    ip: str
    mac: str | None = None
    vendor: str | None = None
    hostname: str | None = None
    os_name: str | None = None
    os_accuracy: int | None = None
    device_type: str | None = None
    open_tcp_ports: tuple[int, ...] = field(default_factory=tuple)
    open_udp_ports: tuple[int, ...] = field(default_factory=tuple)
    services: tuple[str, ...] = field(default_factory=tuple)
    latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class DeepScanReport:
    available: bool
    privileged: bool
    command: tuple[str, ...] = field(default_factory=tuple)
    hosts: tuple[DeepScanResult, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def nmap_available() -> bool:
    return shutil.which("nmap") is not None


def pkexec_available() -> bool:
    return shutil.which("pkexec") is not None


def privileged() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def _validate_local_target(target: str) -> str:
    network = ipaddress.ip_network(target, strict=False)
    if network.version != 4:
        raise ValueError("Deep scan şu anda yalnızca yerel IPv4 ağlarını destekliyor.")
    if not (network.is_private or network.is_link_local):
        raise ValueError("Deep scan yalnızca private/link-local yerel ağlarda çalıştırılabilir.")
    if network.prefixlen < 16:
        raise ValueError("Deep scan için ağ en fazla /16 olmalıdır.")
    return str(network)


def _parse_nmap_xml(raw: str) -> tuple[DeepScanResult, ...]:
    root = ET.fromstring(raw)
    results: list[DeepScanResult] = []
    for host in root.findall("host"):
        status = host.find("status")
        if status is None or status.attrib.get("state") != "up":
            continue
        addresses = host.findall("address")
        ip = next((a.attrib.get("addr") for a in addresses if a.attrib.get("addrtype") == "ipv4"), None)
        if not ip:
            continue
        mac_node = next((a for a in addresses if a.attrib.get("addrtype") == "mac"), None)
        mac = mac_node.attrib.get("addr") if mac_node is not None else None
        vendor = mac_node.attrib.get("vendor") if mac_node is not None else None
        hostname_node = host.find("hostnames/hostname")
        hostname = hostname_node.attrib.get("name") if hostname_node is not None else None
        tcp_ports: list[int] = []
        udp_ports: list[int] = []
        services: list[str] = []
        for port in host.findall("ports/port"):
            state = port.find("state")
            if state is None or state.attrib.get("state") != "open":
                continue
            try:
                number = int(port.attrib["portid"])
            except (KeyError, ValueError):
                continue
            protocol = port.attrib.get("protocol", "tcp")
            (udp_ports if protocol == "udp" else tcp_ports).append(number)
            service = port.find("service")
            if service is not None:
                name = service.attrib.get("name") or "unknown"
                product = service.attrib.get("product")
                version = service.attrib.get("version")
                detail = " ".join(x for x in (name, product, version) if x)
                if detail:
                    services.append(f"{protocol}/{number}: {detail}")
        os_name = None
        os_accuracy = None
        osmatch = host.find("os/osmatch")
        if osmatch is not None:
            os_name = osmatch.attrib.get("name")
            try:
                os_accuracy = int(osmatch.attrib.get("accuracy", "0"))
            except ValueError:
                os_accuracy = None
        device_type = None
        osclass = host.find("os/osmatch/osclass")
        if osclass is not None:
            device_type = osclass.attrib.get("type")
        latency = None
        times = host.find("times")
        if times is not None:
            try:
                latency = float(times.attrib.get("srtt", "0")) / 1000.0
            except ValueError:
                latency = None
        results.append(DeepScanResult(ip=ip, mac=mac, vendor=vendor, hostname=hostname, os_name=os_name, os_accuracy=os_accuracy, device_type=device_type, open_tcp_ports=tuple(sorted(set(tcp_ports))), open_udp_ports=tuple(sorted(set(udp_ports))), services=tuple(dict.fromkeys(services)), latency_ms=latency))
    return tuple(results)


def run_deep_scan(
    target: str,
    *,
    include_udp: bool = True,
    include_os: bool = True,
    include_versions: bool = True,
    top_ports: int = 100,
    timeout_seconds: int = 300,
    elevate: bool = False,
) -> DeepScanReport:
    """Run an opt-in, bounded deep inventory of a local IPv4 network."""
    if not nmap_available():
        return DeepScanReport(False, privileged(), warnings=("Nmap bulunamadı; deep scan kullanılamıyor.",))
    network = _validate_local_target(target)
    is_privileged = privileged()
    warnings: list[str] = []
    prefix = ["nmap"]
    if not is_privileged and elevate:
        if not pkexec_available():
            warnings.append("pkexec bulunamadı; elevated scan normal kullanıcı yetkisiyle devam ediyor.")
        else:
            prefix = ["pkexec", "nmap"]
            is_privileged = True
    ports = max(10, min(1000, int(top_ports)))

    # First discover live hosts. The previous implementation used -Pn against
    # the entire network, which forced Nmap to perform the expensive deep probe
    # even for addresses that were not alive. Feed only confirmed live IPv4
    # addresses into the expensive inventory pass.
    discovery_command = prefix + ["-n", "-sn", "--max-retries", "1", "-T3", "-oX", "-", network]
    if network.endswith("/16"):
        warnings.append("Deep scan /16 ağlarda önce host keşfi yapar; yine de büyük ağlarda tarama süresi artabilir.")
    try:
        discovery = subprocess.run(
            discovery_command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(30, min(timeout_seconds, 180)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return DeepScanReport(True, is_privileged, tuple(discovery_command), warnings=tuple(warnings + ["Host discovery zaman aşımına uğradı."]))
    except OSError as exc:
        return DeepScanReport(True, is_privileged, tuple(discovery_command), warnings=tuple(warnings + [f"Nmap host discovery çalıştırılamadı: {exc}"]))
    if discovery.returncode != 0:
        detail = discovery.stderr.strip() or "Nmap host discovery başarısız oldu."
        return DeepScanReport(True, is_privileged, tuple(discovery_command), warnings=tuple(warnings + [detail]))
    try:
        live_hosts = _parse_nmap_xml(discovery.stdout)
    except ET.ParseError:
        log.warning("Nmap host discovery XML parse failed")
        return DeepScanReport(True, is_privileged, tuple(discovery_command), warnings=tuple(warnings + ["Nmap host discovery çıktısı çözümlenemedi."]))
    live_ips = tuple(dict.fromkeys(host.ip for host in live_hosts))
    if not live_ips:
        return DeepScanReport(
            True,
            is_privileged,
            tuple(discovery_command),
            warnings=tuple(warnings + ["Host discovery canlı cihaz bulamadı; deep inventory çalıştırılmadı."]),
        )

    command = prefix + ["-n", "-Pn", "--open", "--max-retries", "2", "-T3", "--host-timeout", "2m"]
    if is_privileged:
        command.append("-sS")
        if include_os:
            command.extend(["-O", "--osscan-limit", "--osscan-guess"])
    else:
        command.append("-sT")
        if include_os:
            warnings.append("OS fingerprinting için root/raw-packet yetkisi gerekli; bu taramada atlandı.")
    if include_udp:
        if is_privileged:
            command.append("-sU")
        else:
            warnings.append("UDP taraması için gerekli ayrıcalık yok; UDP aşaması atlandı.")
    if include_versions:
        command.extend(["-sV", "--version-light"])
    command.extend(["--top-ports", str(ports), "-oX", "-", "-iL", "-"])
    try:
        completed = subprocess.run(
            command,
            input="\\n".join(live_ips) + "\\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(30, timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return DeepScanReport(True, is_privileged, tuple(command), warnings=tuple(warnings + ["Deep scan zaman aşımına uğradı."]))
    except OSError as exc:
        return DeepScanReport(True, is_privileged, tuple(command), warnings=tuple(warnings + [f"Nmap çalıştırılamadı: {exc}"]))
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Nmap taraması başarısız oldu."
        return DeepScanReport(True, is_privileged, tuple(command), warnings=tuple(warnings + [detail]))
    try:
        hosts = _parse_nmap_xml(completed.stdout)
    except ET.ParseError:
        log.warning("Nmap XML parse failed")
        return DeepScanReport(True, is_privileged, tuple(command), warnings=tuple(warnings + ["Nmap çıktısı çözümlenemedi."]))
    return DeepScanReport(True, is_privileged, tuple(command), hosts=hosts, warnings=tuple(warnings))
