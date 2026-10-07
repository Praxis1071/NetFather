"""Firewall backend contracts and helpers."""
from __future__ import annotations
import ipaddress
from dataclasses import dataclass

@dataclass(frozen=True)
class FirewallResult:
    backend: str
    applied: bool
    blocked_ips: tuple[str, ...]
    detail: str
    preview: str = ""

def normalize_local_ips(values: list[str]) -> list[str]:
    """Normalize private/link-local IPv4 and IPv6 addresses for enforcement."""
    out: list[str] = []
    for value in values:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
        if not (ip.is_private or ip.is_link_local):
            raise ValueError(
                f"Firewall yalnız yerel/private IPv4 veya IPv6 adreslerini kabul eder: {value}"
            )
        normalized = str(ip)
        if normalized not in out:
            out.append(normalized)
    return sorted(
        out,
        key=lambda value: (
            ipaddress.ip_address(value).version,
            int(ipaddress.ip_address(value)),
        ),
    )
