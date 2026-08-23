"""
Yerel ağ cihaz keşfi.

FAZ 1 kapsamında yalnızca modül iskeleti bulunur. ARP taraması üzerinden
cihaz keşfi FAZ 3'te uygulanacaktır.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiscoveredHost:
    """Ağ taramasında bulunan bir cihazın ham bilgisi."""

    ip: str
    mac: str
    vendor: str | None = None


def scan_network(timeout_seconds: int = 5) -> list[DiscoveredHost]:
    """
    Yerel ağı tarayıp bulunan cihazları döndürür.

    FAZ 3'te gerçek implementasyon eklenecektir.
    """
    return []
