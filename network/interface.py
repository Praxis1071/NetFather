"""
Ağ arayüzü tespiti.

FAZ 1 kapsamında yalnızca modül iskeleti bulunur. Aktif interface, local IP
ve gateway tespiti FAZ 2'de uygulanacaktır.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NetworkStatus:
    """Aktif ağ arayüzü bilgilerini tutar."""

    interface: str | None = None
    local_ip: str | None = None
    gateway: str | None = None
    netmask: str | None = None


def get_network_status() -> NetworkStatus:
    """
    Aktif ağ arayüzü bilgilerini döndürür.

    FAZ 2'de gerçek implementasyon eklenecektir (ör. psutil / socket / ip
    komutu üzerinden).
    """
    return NetworkStatus()
