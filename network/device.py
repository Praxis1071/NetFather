"""
Ağ katmanında cihaz yardımcı fonksiyonları.

FAZ 1 kapsamında yalnızca modül iskeleti bulunur. MAC vendor lookup ve
cihaz tipi tahmini gibi işlevler FAZ 3'te eklenecektir.
"""

from __future__ import annotations


def normalize_mac(mac: str) -> str:
    """MAC adresini büyük harf ve ':' ayraçlı standart forma çevirir."""
    cleaned = mac.strip().upper().replace("-", ":")
    return cleaned


def lookup_vendor(mac: str) -> str | None:
    """
    MAC adresinin OUI kısmından üretici bilgisini döndürür.

    FAZ 3'te gerçek implementasyon (yerel OUI veritabanı) eklenecektir.
    """
    return None
