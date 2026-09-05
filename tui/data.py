"""
TUI ekranları için veri toplama katmanı.

Bu modül, CLI'nin zaten kullandığı **aynı** alt katman fonksiyonlarını
çağırır (`network.interface.get_network_status`, `network.discovery.
scan_network`, `manager.device_manager.DeviceManager`, `core.config`).
Hiçbir iş mantığı burada tekrar edilmez; bu modül yalnızca ekranların
ihtiyaç duyduğu şekilde veriyi bir araya getirir (aggregate) ve normalize
eder.

Kasıtlı olarak Rich'e bağımlı DEĞİLDİR: tüm fonksiyonlar düz Python veri
yapıları (dataclass, str, int, list) döndürür, böylece gerçek bir Rich
kurulumu olmadan da test edilebilir.

Hata politikası: bu katmandaki hiçbir fonksiyon exception fırlatmaz.
Alt katmanlar zaten kendi hata toleranslarına sahiptir (`get_network_status`
ve `scan_network` hiçbir zaman exception fırlatmaz); ek olarak `DeviceManager`
ve config/log okumalarından gelebilecek hatalar da burada yakalanıp güvenli
varsayılan değerlere (boş liste, None, "Unknown" vb.) dönüştürülür.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from core.config import Config
from core.database import Database
from core.exceptions import NetFatherError
from core.logger import get_logger
from manager.device_manager import DeviceManager
from manager.profile_manager import ProfileManager
from manager.rule_manager import RuleManager
from models.device import Device
from models.profile import Profile
from models.rule import Rule
from network.discovery import DiscoveredHost, scan_network
from network.interface import NetworkStatus, get_network_status
from tui.state import AppState

log = get_logger("tui.data")

# `get_network_status()` bir subprocess çağrısı içerir; TUI'nin her klavye
# olayında (ör. yalnızca yukarı/aşağı ok) yeniden çalıştırmak gereksiz
# gecikme yaratır. Bu yüzden sonucu kısa bir süre önbellekte tutuyoruz.
# Bu, iş parçacığı (thread) veya asenkron karmaşıklık GEREKTİRMEZ —
# yalnızca zaman damgasıyla basit bir "en fazla N saniyede bir çalıştır"
# kuralıdır.
_NETWORK_STATUS_CACHE_SECONDS = 5


def get_cached_network_status(state: AppState) -> NetworkStatus:
    """
    `get_network_status()`'u en fazla `_NETWORK_STATUS_CACHE_SECONDS`de bir
    gerçekten çalıştırır; aradaki çağrılarda `state`'teki önbellekten döner.

    Refresh ('r') tuşu bu önbelleği manuel olarak temizleyebilir (bkz.
    `tui/app.py`), böylece kullanıcı istediğinde anında güncel veri alabilir.
    """
    now = dt.datetime.now()
    is_stale = (
        state.network_status_fetched_at is None
        or (now - state.network_status_fetched_at).total_seconds() > _NETWORK_STATUS_CACHE_SECONDS
    )
    if is_stale or state.cached_network_status is None:
        state.cached_network_status = get_network_status()
        state.network_status_fetched_at = now
    return state.cached_network_status


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


@dataclass
class OverviewData:
    """Overview ekranının ihtiyaç duyduğu özet veriler."""

    interface: str | None = None
    local_ip: str | None = None
    gateway: str | None = None
    network_status_known: bool = False

    registered_device_count: int | None = None  # None = DB okunamadı
    last_scan_time: dt.datetime | None = None
    last_scan_device_count: int | None = None
    last_scan_error: str | None = None

    database_ok: bool = True
    database_error: str | None = None


def get_overview_data(config: Config, db: Database, state: AppState) -> OverviewData:
    """
    Overview ekranı için mevcut sistemden elde edilebilen gerçek verileri toplar.

    Hiçbir alan uydurulmaz: `network/interface.py` tespit yapamıyorsa
    ilgili alanlar None kalır (çağıran taraf bunu "Unknown"/"N/A" olarak
    göstermelidir). Discovery bilgisi yalnızca bu oturumda daha önce
    "Scan Now" ile tetiklenmişse doludur; aksi halde None'dur (fake veri
    üretilmez).
    """
    net_status = get_cached_network_status(state)

    data = OverviewData(
        interface=net_status.interface,
        local_ip=net_status.local_ip,
        gateway=net_status.gateway,
        network_status_known=net_status != NetworkStatus(),
        last_scan_time=state.last_scan_time,
        last_scan_device_count=(len(state.last_scan_hosts) if state.last_scan_time else None),
        last_scan_error=state.last_scan_error,
    )

    try:
        manager = DeviceManager(db)
        data.registered_device_count = len(manager.list_devices())
    except NetFatherError as exc:
        log.warning("Overview için cihaz sayısı okunamadı: %s", exc)
        data.registered_device_count = None
        data.database_ok = False
        data.database_error = str(exc)

    return data


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def invalidate_network_status_cache(state: AppState) -> None:
    """Refresh ('r') eyleminde çağrılır: önbelleği temizler, bir sonraki okuma taze veri alır."""
    state.network_status_fetched_at = None


def get_network_data(state: AppState) -> NetworkStatus:
    """Network ekranı için mevcut `get_network_status()`'u önbellekli şekilde yeniden kullanır."""
    return get_cached_network_status(state)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryData:
    """Discovery ekranının gösterdiği durum ve son tarama sonucu."""

    backend: str = "passive + Scapy active (hybrid capable)"
    last_scan_time: dt.datetime | None = None
    last_scan_error: str | None = None
    hosts: list[DiscoveredHost] = field(default_factory=list)


def get_discovery_data(state: AppState) -> DiscoveryData:
    """
    Discovery ekranı için, bu oturumda daha önce yapılmış son taramanın
    (varsa) sonucunu döndürür. Kendisi YENİ bir tarama BAŞLATMAZ — bu,
    yalnızca `trigger_scan()` çağrıldığında (kullanıcı "Scan Now" seçtiğinde)
    olur.
    """
    return DiscoveryData(
        last_scan_time=state.last_scan_time,
        last_scan_error=state.last_scan_error,
        hosts=list(state.last_scan_hosts),
    )


def trigger_scan(config: Config) -> tuple[list[DiscoveredHost], str | None]:
    """
    Kullanıcının "Scan Now" eylemini gerçekleştirir.

    Mevcut `network.discovery.scan_network()` fonksiyonunu doğrudan
    kullanır (TUI için ikinci bir discovery implementasyonu YOKTUR).
    Sonuç veritabanına yazılmaz.

    Returns:
        (bulunan cihazlar, hata mesajı ya da None) ikilisi.
        `scan_network()` zaten hiçbir zaman exception fırlatmadığı için
        buradaki hata mesajı yalnızca "boş sonuç" durumunu bilgilendirici
        şekilde açıklamak için kullanılır; gerçek bir exception söz konusu
        olursa (beklenmez) yine de burada yakalanır ki TUI çökmesin.
    """
    try:
        hosts = scan_network(
            timeout_seconds=config.network.scan_timeout_seconds,
            mode=config.discovery.mode,
            subnet=config.discovery.subnet or None,
            hostname_resolution=config.discovery.hostname_resolution,
            vendor_detection=config.discovery.vendor_detection,
            os_detection=config.discovery.os_detection,
            active_timeout_seconds=config.discovery.active_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - TUI'nin çökmemesi için son güvenlik ağı
        log.exception("TUI taraması sırasında beklenmeyen hata: %s", exc)
        return [], "Tarama sırasında beklenmeyen bir hata oluştu."

    if not hosts:
        return [], "Hiçbir cihaz bulunamadı."
    return hosts, None


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------


def get_registered_devices(db: Database) -> tuple[list[Device], str | None]:
    """
    Devices ekranı için veritabanındaki kayıtlı cihazları döndürür.

    Discovery sonuçlarıyla KARIŞTIRILMAZ; bu, yalnızca `DeviceManager`
    üzerinden okunan kalıcı kayıtlardır. TUI, bu listeyi ve
    `get_discovery_data()`'nın sonucunu ekranda ayrı, açıkça etiketlenmiş
    bölümler olarak göstermelidir.

    Returns:
        (cihaz listesi, hata mesajı ya da None) ikilisi. DB okunamazsa
        boş liste + hata mesajı döner, exception fırlatılmaz.
    """
    try:
        manager = DeviceManager(db)
        return manager.list_devices(), None
    except NetFatherError as exc:
        log.warning("Devices ekranı için kayıtlı cihazlar okunamadı: %s", exc)
        return [], str(exc)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def get_config_display_rows(config: Config) -> list[tuple[str, str]]:
    """
    Configuration ekranı için (etiket, değer) çiftleri üretir.

    Salt-okunur bir gösterimdir; bu fonksiyon config dosyasını değiştirmez.
    """
    return [
        ("Config dosyası", str(config.config_path)),
        ("Veri dizini", str(config.data_dir)),
        ("Database", str(config.database_path)),
        ("Log dosyası", str(config.log_path)),
        ("Log seviyesi", config.logging.level),
        ("Scan timeout (saniye)", str(config.network.scan_timeout_seconds)),
        ("Varsayılan arayüz", config.network.default_interface or "(otomatik tespit)"),
        ("Discovery mode", config.discovery.mode),
        ("Discovery interval", f"{config.discovery.interval_seconds}s"),
        ("Auto register", "yes" if config.discovery.auto_register else "no"),
        ("Hostname detection", "yes" if config.discovery.hostname_resolution else "no"),
        ("OS detection", "yes" if config.discovery.os_detection else "no"),
        ("Firewall backend", config.firewall.backend),
        ("Firewall enforcement", "enabled" if config.firewall.enforcement_enabled else "disabled (dry-run)"),
        ("Monitor refresh (saniye)", str(config.monitor.refresh_seconds)),
        ("Daemon interval", f"{config.daemon.interval_seconds}s"),
    ]


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


def get_recent_log_lines(config: Config, max_lines: int = 20) -> tuple[list[str], str | None]:
    """
    Log dosyasının son satırlarını döndürür.

    Mevcut logger altyapısı üzerinden dosya yolu (`config.log_path`)
    kullanılır; yeni bir logging sistemi kurulmaz. Dosya yoksa veya
    okunamazsa boş liste + bilgilendirici mesaj döner (exception yok).
    """
    log_path: Path = config.log_path

    if not log_path.exists():
        return [], "Henüz bir log dosyası oluşturulmamış."

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        log.warning("Log dosyası okunamadı: %s", exc)
        return [], f"Log dosyası okunamadı: {exc}"

    if not lines:
        return [], "Log dosyası boş."

    return lines[-max_lines:], None


# ---------------------------------------------------------------------------
# Profiles / Rules
# ---------------------------------------------------------------------------


def get_profiles(db: Database) -> tuple[list[Profile], str | None]:
    """Return configured profiles for TUI display without leaking exceptions."""
    try:
        return ProfileManager(db).list_profiles(), None
    except NetFatherError as exc:
        log.warning("Profiles ekranı için veriler okunamadı: %s", exc)
        return [], str(exc)


def get_rules(db: Database) -> tuple[list[Rule], str | None]:
    """Return configured rules for TUI display without leaking exceptions."""
    try:
        return RuleManager(db).list_rules(), None
    except NetFatherError as exc:
        log.warning("Rules ekranı için veriler okunamadı: %s", exc)
        return [], str(exc)


def sync_known_discovered(db: Database, state: AppState) -> tuple[int, str | None]:
    """Update registered devices from the last discovery snapshot.

    Unknown hosts are not inserted. This is an explicit TUI action (``s``),
    not a side effect of scanning.
    """
    if not state.last_scan_hosts:
        return 0, "Önce bir discovery taraması çalıştırın."
    try:
        updated = DeviceManager(db).sync_discovered_hosts(state.last_scan_hosts)
        return updated, None
    except NetFatherError as exc:
        log.warning("Discovery sync başarısız: %s", exc)
        return 0, str(exc)


def get_topology(db: Database):
    from network.topology import build_topology
    try:
        return build_topology(db), None
    except Exception as exc:
        log.warning("Topology oluşturulamadı: %s", exc); return None, str(exc)

def get_monitoring(db: Database):
    from monitor.monitor import Monitor
    try:
        return Monitor(db).snapshot(), None
    except Exception as exc:
        log.warning("Monitoring snapshot alınamadı: %s", exc); return None, str(exc)

def get_events(db: Database, limit: int = 30):
    from manager.event_manager import EventManager
    try:
        return EventManager(db).list_events(limit=limit), None
    except Exception as exc:
        log.warning("Events okunamadı: %s", exc); return [], str(exc)

def get_policies(db: Database):
    from manager.policy_engine import PolicyEngine
    try:
        return {p.mac: p for p in PolicyEngine(db).evaluate_all()}, None
    except Exception as exc:
        return {}, str(exc)
