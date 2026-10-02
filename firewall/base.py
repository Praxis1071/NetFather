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
    out: list[str] = []
    for value in values:
        ip = ipaddress.ip_address(value)
        if ip.version != 4:
            continue
        if not (ip.is_private or ip.is_link_local):
            raise ValueError(f"Firewall yalnız yerel/private IPv4 adreslerini kabul eder: {value}")
        if str(ip) not in out:
            out.append(str(ip))
    return sorted(out)
