"""
Ağ arayüzü tespiti.

Aktif ağ arayüzü, yerel IP ve varsayılan gateway bilgisi Linux üzerinde
`ip route get` komutunun çıktısından türetilir.

Tasarım, komut çalıştırmayı (OS command wrapper) çıktı ayrıştırmadan
(pure parser) bilinçli olarak ayırır:

    OS command wrapper (_run_ip_route_get)
            ↓ ham stdout metni
       pure parser (_parse_route_get_output)
            ↓
    normalized result (NetworkStatus)

Bu ayrım sayesinde ayrıştırma mantığı gerçek bir `ip` komutu veya ağ
bağlantısı gerektirmeden, sabit string girdileriyle test edilebilir.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from core.logger import get_logger

log = get_logger("network.interface")

# `ip route get` hedefe hiçbir paket göndermez; yalnızca çekirdeğin
# yönlendirme tablosuna "bu hedefe gidilirken hangi arayüz/gateway/kaynak
# IP kullanılırdı" diye sorar. Hedefin gerçekten erişilebilir olması
# gerekmez, yalnızca varsayılan rotayı ortaya çıkarmak için bir örnek
# genel-ağ adresi olarak kullanılır.
_ROUTE_PROBE_TARGET = "8.8.8.8"
_COMMAND_TIMEOUT_SECONDS = 3

# Örnek çıktı:
#   8.8.8.8 via 192.168.1.1 dev wlan0 src 192.168.1.50 uid 1000
# "via <gateway>" kısmı isteğe bağlıdır (hedef doğrudan bağlı bir ağdaysa
# görünmeyebilir); "dev <interface>" her zaman bulunur.
_ROUTE_GET_PATTERN = re.compile(
    r"(?:via\s+(?P<gateway>\S+)\s+)?dev\s+(?P<interface>\S+)"
    r"(?:.*?\bsrc\s+(?P<src_ip>\S+))?"
)


@dataclass
class NetworkStatus:
    """Aktif ağ arayüzü bilgilerini tutar."""

    interface: str | None = None
    local_ip: str | None = None
    gateway: str | None = None
    # NOT: netmask tespiti FAZ2.1 kapsamı dışında bırakıldı. `ip route get`
    # çıktısı netmask içermez; bunun için ayrı bir `ip addr show` çağrısı
    # gerekir. `status` komutu şu an netmask'i göstermiyor, bu yüzden
    # kapsam en küçük tutuldu; ihtiyaç doğarsa ayrı bir adımda eklenebilir.
    netmask: str | None = None


def _run_ip_route_get(target: str = _ROUTE_PROBE_TARGET) -> str | None:
    """
    `ip route get <target>` komutunu çalıştırır ve ham stdout metnini döndürür.

    `ip` komutu bulunamazsa, zaman aşımına uğrarsa ya da sıfırdan farklı
    bir çıkış koduyla dönerse (ör. hiç varsayılan rota yoksa, tamamen
    çevrimdışı bir makine) None döner. Bu, bir hata değil; normal bir
    "şu an tespit edilemiyor" durumu olarak ele alınır ve exception
    fırlatılmaz.

    Args:
        target: Rota sorgusu için kullanılan örnek hedef adres.

    Returns:
        Komutun ham stdout çıktısı, ya da tespit mümkün değilse None.
    """
    ip_binary = shutil.which("ip")
    if ip_binary is None:
        log.debug("'ip' komutu bulunamadı; ağ arayüzü tespiti atlanıyor.")
        return None

    try:
        result = subprocess.run(
            [ip_binary, "route", "get", target],
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("'ip route get' çalıştırılamadı: %s", exc)
        return None

    if result.returncode != 0:
        log.debug(
            "'ip route get %s' sıfırdan farklı çıkış koduyla döndü (%s): %s",
            target,
            result.returncode,
            result.stderr.strip(),
        )
        return None

    return result.stdout


def _parse_route_get_output(raw_output: str) -> NetworkStatus:
    """
    `ip route get` komutunun ham çıktısını `NetworkStatus`'a dönüştürür.

    Saf bir metin ayrıştırıcıdır: hiçbir sistem çağrısı yapmaz, yalnızca
    verilen string'i işler. Boş veya beklenmeyen formatta girdi için tüm
    alanları None olan bir NetworkStatus döner (hata fırlatmaz).

    Args:
        raw_output: `_run_ip_route_get`'ten gelen ham stdout metni.

    Returns:
        Ayrıştırılmış NetworkStatus.
    """
    match = _ROUTE_GET_PATTERN.search(raw_output)
    if match is None:
        return NetworkStatus()

    return NetworkStatus(
        interface=match.group("interface"),
        local_ip=match.group("src_ip"),
        gateway=match.group("gateway"),
    )


def get_network_status() -> NetworkStatus:
    """
    Aktif ağ arayüzü, yerel IP ve varsayılan gateway bilgisini döndürür.

    Tespit başarısız olursa (arayüz yok, 'ip' komutu bulunamadı, zaman
    aşımı vb.) hiçbir istisna fırlatmaz; tüm alanları None olan boş bir
    NetworkStatus döner. Böylece çağıran taraf (CLI) bunu normal bir
    "tespit edilemedi" durumu olarak gösterebilir.

    Returns:
        Tespit edilen (veya tespit edilemediyse boş) NetworkStatus.
    """
    raw_output = _run_ip_route_get()
    if raw_output is None:
        return NetworkStatus()
    return _parse_route_get_output(raw_output)
