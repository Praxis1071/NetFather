"""
Yerel ağ cihaz keşfi (basic discovery).

Linux üzerinde çekirdeğin komşu (neighbor/ARP) tablosunu `ip neigh`
komutuyla okur, ayrıştırır ve normalize edilmiş bir sonuç listesi olarak
döndürür.

Tasarım, `network/interface.py`'deki (FAZ2.1) desenle birebir tutarlıdır:

    OS command wrapper (_run_ip_neigh)
            ↓ ham stdout metni
       pure parser (_parse_ip_neigh_output)
            ↓
    normalized result (list[DiscoveredHost])

Bu modül BASIC discovery'dir; Scapy'ye **hiçbir şekilde bağımlı değildir**
ve onu import etmez. Scapy tabanlı, kullanıcının açıkça seçebileceği
ayrıntılı/aktif bir discovery backend'i ileride ayrı bir modül olarak
eklenecektir — bu modül o backend'in yerini almaz, onunla aynı normalize
sonuç formatını (DiscoveredHost) paylaşacak şekilde tasarlanmıştır.

Bu modül keşfetmekten sorumludur; keşfedilen cihazları veritabanına
kaydetmek (persistence) bu modülün sorumluluğu değildir ve burada
yapılmaz — o karar `manager` katmanına bırakılmıştır.
"""

from __future__ import annotations

import ipaddress
import shutil
import subprocess
from dataclasses import dataclass

from core.logger import get_logger
from network.device import lookup_vendor

log = get_logger("network.discovery")

_COMMAND_TIMEOUT_SECONDS_DEFAULT = 5

# `ip neigh` çıktısında normal bir neighbor kaydı sayılmayacak, "anlamsız"
# kabul edilen adresler. Aşırı agresif filtrelemekten kaçınmak için burada
# yalnızca kesin olarak yorumlanabilen durumlar (loopback, multicast)
# elenir; bilinmeyen/olağan dışı ama geçerli bir unicast adres asla
# atılmaz.
def _is_meaningless_address(ip_text: str) -> bool:
    """Loopback veya multicast gibi gerçek bir "komşu cihaz" temsil etmeyen adresleri eler."""
    try:
        ip_obj = ipaddress.ip_address(ip_text)
    except ValueError:
        # Adres olarak ayrıştırılamıyorsa filtreleme kararı veremeyiz;
        # satırın kendisi zaten genel token doğrulamasında elenecektir.
        return False
    return ip_obj.is_loopback or ip_obj.is_multicast


@dataclass
class DiscoveredHost:
    """
    Ağ taramasında (`ip neigh` üzerinden) bulunan bir cihazın normalize
    edilmiş kaydı.

    `ip` dışındaki tüm alanlar isteğe bağlıdır: `ip neigh` çıktısında bir
    komşu kaydının MAC adresi olmayabilir (ör. `FAILED` durumu) — bu,
    kaydın çöpe atılması gereken bir sebep değildir.
    """

    ip: str
    interface: str | None = None
    mac: str | None = None
    state: str | None = None
    # Yerel OUI veritabanı mevcutsa ``scan_network`` tarafından doldurulur.
    # Uzak vendor servislerine MAC adresi gönderilmez.
    vendor: str | None = None


def _normalize_discovery_mac(mac: str) -> str:
    """
    Discovery katmanı için MAC'i lowercase, ':' ayraçlı forma normalize eder.

    NOT: Bu, `network/device.py::normalize_mac()`'in (uppercase, persistence
    katmanı için) davranışından bilinçli olarak farklıdır. `ip neigh` zaten
    doğal olarak lowercase MAC döndürür; discovery sonucu bir cihaz olarak
    kaydedilmek istendiğinde (bu modülün sorumluluğu değildir) persistence
    katmanı kendi normalizasyonunu (uppercase) zaten uygular.
    """
    return mac.strip().lower().replace("-", ":")


def _parse_neigh_line(line: str) -> DiscoveredHost | None:
    """
    `ip neigh` çıktısının tek bir satırını ayrıştırır.

    Beklenen minimum yapı: ``<ip> dev <interface> [lladdr <mac>] [state]``.
    Bu yapıya uymayan (ip/dev/interface üçlüsü bulunamayan) satırlar
    malformed kabul edilip sessizce (None dönerek) atlanır — exception
    fırlatılmaz.

    `state`, sabit bir değer kümesine hard-code edilmez: kalan token'ların
    sonuncusu neyse o, olduğu gibi korunur. Bu, `ip neigh`'in
    REACHABLE/STALE/DELAY/PROBE/FAILED/INCOMPLETE/NOARP/PERMANENT gibi
    bilinen durumlarının yanı sıra ileride eklenebilecek bilinmeyen ama
    geçerli durumları da kaybetmeden taşımasını sağlar.

    Args:
        line: `ip neigh` çıktısının tek bir satırı.

    Returns:
        Ayrıştırılmış DiscoveredHost, ya da satır malformed/anlamsızsa None.
    """
    tokens = line.split()

    # En az "<ip> dev <interface>" üçlüsü olmalı.
    if len(tokens) < 3 or tokens[1] != "dev":
        return None

    ip_text = tokens[0]
    interface = tokens[2]

    if _is_meaningless_address(ip_text):
        return None

    remaining = tokens[3:]

    mac: str | None = None
    if len(remaining) >= 2 and remaining[0] == "lladdr":
        mac = _normalize_discovery_mac(remaining[1])
        remaining = remaining[2:]

    state = remaining[-1] if remaining else None

    return DiscoveredHost(ip=ip_text, interface=interface, mac=mac, state=state)


def _parse_ip_neigh_output(raw_output: str) -> list[DiscoveredHost]:
    """
    `ip neigh` komutunun ham çıktısını normalize edilmiş bir listeye dönüştürür.

    Saf bir metin ayrıştırıcıdır: hiçbir sistem çağrısı yapmaz, global
    duruma dokunmaz, hiçbir koşulda exception fırlatmaz. Boş veya tamamen
    bozuk girdi için boş liste döner.

    Aynı `(ip, interface)` çiftine sahip birden fazla satır gelirse
    (duplicate), **son görülen kayıt kazanır** ve sonuç deterministik
    olur; bu, `ip neigh` çıktısında normalde beklenmez ama girdi
    tekrarlarına karşı sonucu öngörülebilir kılmak için açıkça
    tanımlanmıştır.

    Args:
        raw_output: `_run_ip_neigh`'ten gelen ham stdout metni.

    Returns:
        Normalize edilmiş, tekilleştirilmiş DiscoveredHost listesi.
    """
    by_identity: dict[tuple[str, str | None], DiscoveredHost] = {}

    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue

        host = _parse_neigh_line(line)
        if host is None:
            log.debug("ip neigh satırı ayrıştırılamadı, atlanıyor: %r", line)
            continue

        by_identity[(host.ip, host.interface)] = host

    return list(by_identity.values())


def _run_ip_neigh(timeout_seconds: int) -> str | None:
    """
    `ip neigh` komutunu çalıştırır ve ham stdout metnini döndürür.

    `ip` komutu bulunamazsa, zaman aşımına uğrarsa ya da sıfırdan farklı
    bir çıkış koduyla dönerse None döner; bu bir hata değil, normal bir
    "şu an keşif yapılamıyor" durumu olarak ele alınır. Hiçbir exception
    dışarı sızmaz.

    Args:
        timeout_seconds: Komutun en fazla ne kadar bekleneceği (saniye).

    Returns:
        Komutun ham stdout çıktısı, ya da tespit mümkün değilse None.
    """
    ip_binary = shutil.which("ip")
    if ip_binary is None:
        log.debug("'ip' komutu bulunamadı; ağ keşfi atlanıyor.")
        return None

    try:
        result = subprocess.run(
            [ip_binary, "neigh"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("'ip neigh' çalıştırılamadı: %s", exc)
        return None

    if result.returncode != 0:
        log.debug(
            "'ip neigh' sıfırdan farklı çıkış koduyla döndü (%s): %s",
            result.returncode,
            result.stderr.strip(),
        )
        return None

    return result.stdout


def scan_network(timeout_seconds: int = _COMMAND_TIMEOUT_SECONDS_DEFAULT) -> list[DiscoveredHost]:
    """
    Yerel ağdaki komşu cihazları `ip neigh` üzerinden keşfeder.

    Bu fonksiyon yalnızca **keşfeder**; hiçbir şekilde veritabanına yazmaz
    (discovery/persistence ayrımı bilinçlidir). Sonuçları kaydetmek isteyen
    çağıran taraf, dönen listeyi kendi kararıyla `manager` katmanına
    aktarmalıdır.

    Keşif başarısız olursa (arayüz yok, 'ip' komutu bulunamadı, zaman
    aşımı vb.) hiçbir istisna fırlatmaz; boş bir liste döner.

    Args:
        timeout_seconds: `ip neigh` komutunun en fazla ne kadar
            bekleneceği (saniye). Varsayılan, `core.config.NetworkConfig`
            içindeki `scan_timeout_seconds` varsayılanıyla aynıdır (5).

    Returns:
        Normalize edilmiş, tekilleştirilmiş DiscoveredHost listesi
        (keşif başarısızsa boş liste).
    """
    raw_output = _run_ip_neigh(timeout_seconds)
    if raw_output is None:
        return []

    hosts = _parse_ip_neigh_output(raw_output)
    for host in hosts:
        if host.mac:
            host.vendor = lookup_vendor(host.mac)
    return hosts
