"""TUI data aggregation layer.

No Rich/I/O is performed here. Discovery is delegated to ``tui.scan`` so
rendering and keyboard input never wait for network work.
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
from network.discovery import DiscoveredHost
from network.interface import NetworkStatus, get_network_status
from tui.scan import ScanSnapshot, ScanStatus, get_scan_controller
from tui.state import AppState

log = get_logger("tui.data")
_NETWORK_STATUS_CACHE_SECONDS = 5


def get_cached_network_status(state: AppState) -> NetworkStatus:
    now = dt.datetime.now()
    stale = (
        state.network_status_fetched_at is None
        or (now - state.network_status_fetched_at).total_seconds() > _NETWORK_STATUS_CACHE_SECONDS
    )
    if stale or state.cached_network_status is None:
        state.cached_network_status = get_network_status()
        state.network_status_fetched_at = now
    return state.cached_network_status


@dataclass
class OverviewData:
    interface: str | None = None
    local_ip: str | None = None
    gateway: str | None = None
    network_status_known: bool = False
    registered_device_count: int | None = None
    last_scan_time: dt.datetime | None = None
    last_scan_device_count: int | None = None
    last_scan_error: str | None = None
    database_ok: bool = True
    database_error: str | None = None


def get_overview_data(config: Config, db: Database, state: AppState) -> OverviewData:
    net_status = get_cached_network_status(state)
    scan = get_scan_controller().snapshot()
    hosts = get_scan_controller().hosts()
    last_time = scan.finished_at or scan.started_at or state.last_scan_time
    data = OverviewData(
        interface=net_status.interface,
        local_ip=net_status.local_ip,
        gateway=net_status.gateway,
        network_status_known=net_status != NetworkStatus(),
        last_scan_time=last_time,
        last_scan_device_count=len(hosts) if hosts else (len(state.last_scan_hosts) if state.last_scan_time else None),
        last_scan_error=scan.error or state.last_scan_error,
    )
    try:
        data.registered_device_count = len(DeviceManager(db).list_devices())
    except NetFatherError as exc:
        log.warning("Overview için cihaz sayısı okunamadı: %s", exc)
        data.registered_device_count = None
        data.database_ok = False
        data.database_error = str(exc)
    return data


def invalidate_network_status_cache(state: AppState) -> None:
    state.network_status_fetched_at = None


def get_network_data(state: AppState) -> NetworkStatus:
    return get_cached_network_status(state)


@dataclass
class DiscoveryData:
    backend: str = "passive + Scapy active (hybrid capable)"
    last_scan_time: dt.datetime | None = None
    last_scan_error: str | None = None
    hosts: list[DiscoveredHost] = field(default_factory=list)
    scan: ScanSnapshot = field(default_factory=ScanSnapshot)


def _progress_bar(progress: int, width: int = 20) -> str:
    progress = max(0, min(100, progress))
    filled = round(width * progress / 100)
    return "[" + "=" * filled + "." * (width - filled) + "]"


def _scan_backend_text(snapshot: ScanSnapshot) -> str:
    options = snapshot.options
    if snapshot.status in {ScanStatus.SCANNING, ScanStatus.CANCELLING}:
        mode = options.mode if options else "unknown"
        methods = []
        if options:
            methods.append("hostname" if options.hostname_resolution else "no-hostname")
            methods.append("vendor" if options.vendor_detection else "no-vendor")
            methods.append("OS" if options.os_detection else "no-OS")
        return (
            f"Status: SCANNING\n"
            f"Progress: {_progress_bar(snapshot.progress)} {snapshot.progress}%\n"
            f"Current: {snapshot.current_operation}\n"
            f"Mode: {mode}  Enrichment: {', '.join(methods) or 'default'}\n"
            f"Devices found: {snapshot.found_count}\n"
            f"New devices: {snapshot.new_count}\n"
            f"Updated: {snapshot.updated_count}\n"
            f"Offline: {snapshot.offline_count}\n"
            f"Action: [bold cyan][ r ][/bold cyan] STOP SCAN"
        )
    if snapshot.status is ScanStatus.CANCELLED:
        return (
            "Status: CANCELLED\n"
            f"Devices found before stop: {snapshot.found_count}\n"
            "Action: [bold cyan][ r ][/bold cyan] SCAN NOW"
        )
    if snapshot.status is ScanStatus.FAILED:
        return f"Status: FAILED\nError: {snapshot.error or 'Unknown error'}\nAction: [bold cyan][ r ][/bold cyan] SCAN NOW"
    if snapshot.status is ScanStatus.COMPLETED:
        return (
            "Status: COMPLETE\n"
            f"Devices found: {snapshot.found_count}\n"
            f"New devices: {snapshot.new_count}\n"
            f"Updated: {snapshot.updated_count}\n"
            f"Offline: {snapshot.offline_count}\n"
            "Action: [bold cyan][ r ][/bold cyan] SCAN NOW"
        )
    return "Status: READY\nAction: [bold cyan][ r ][/bold cyan] SCAN NOW"


def get_discovery_data(state: AppState) -> DiscoveryData:
    controller = get_scan_controller()
    snapshot = controller.snapshot()
    hosts = controller.hosts() or list(state.last_scan_hosts)
    return DiscoveryData(
        backend=_scan_backend_text(snapshot),
        last_scan_time=snapshot.finished_at or snapshot.started_at or state.last_scan_time,
        last_scan_error=snapshot.error or state.last_scan_error,
        hosts=hosts,
        scan=snapshot,
    )


def trigger_scan(config: Config) -> tuple[list[DiscoveredHost], str | None]:
    """Toggle the background scan: start when idle, cancel when running."""
    controller = get_scan_controller()
    if controller.snapshot().running:
        controller.cancel()
        return controller.hosts(), "Scan stopping..."
    if not controller.start(config):
        return controller.hosts(), "A scan is already running."
    return [], None


def get_registered_devices(db: Database) -> tuple[list[Device], str | None]:
    try:
        return DeviceManager(db).list_devices(), None
    except NetFatherError as exc:
        log.warning("Devices ekranı için kayıtlı cihazlar okunamadı: %s", exc)
        return [], str(exc)


def get_config_display_rows(config: Config) -> list[tuple[str, str]]:
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
        ("Vendor detection", "yes" if config.discovery.vendor_detection else "no"),
        ("OS detection", "yes" if config.discovery.os_detection else "no"),
        ("Firewall backend", config.firewall.backend),
        ("Firewall enforcement", "enabled" if config.firewall.enforcement_enabled else "disabled (dry-run)"),
        ("Monitor refresh (saniye)", str(config.monitor.refresh_seconds)),
        ("Daemon interval", f"{config.daemon.interval_seconds}s"),
    ]


def get_recent_log_lines(config: Config, max_lines: int = 20) -> tuple[list[str], str | None]:
    log_path: Path = config.log_path
    if not log_path.exists():
        return [], "Henüz bir log dosyası oluşturulmamış."
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        log.warning("Log dosyası okunamadı: %s", exc)
        return [], f"Log dosyası okunamadı: {exc}"
    return (lines[-max_lines:], None) if lines else ([], "Log dosyası boş.")


def get_profiles(db: Database) -> tuple[list[Profile], str | None]:
    try:
        return ProfileManager(db).list_profiles(), None
    except NetFatherError as exc:
        log.warning("Profiles ekranı için veriler okunamadı: %s", exc)
        return [], str(exc)


def get_rules(db: Database) -> tuple[list[Rule], str | None]:
    try:
        return RuleManager(db).list_rules(), None
    except NetFatherError as exc:
        log.warning("Rules ekranı için veriler okunamadı: %s", exc)
        return [], str(exc)


def sync_known_discovered(db: Database, state: AppState) -> tuple[int, str | None]:
    hosts = get_scan_controller().hosts() or state.last_scan_hosts
    if not hosts:
        return 0, "Önce bir discovery taraması çalıştırın."
    try:
        return DeviceManager(db).sync_discovered_hosts(hosts), None
    except NetFatherError as exc:
        log.warning("Discovery sync başarısız: %s", exc)
        return 0, str(exc)


def get_topology(db: Database):
    from network.topology import build_topology
    try:
        return build_topology(db), None
    except Exception as exc:
        log.warning("Topology oluşturulamadı: %s", exc)
        return None, str(exc)


def get_monitoring(db: Database):
    from monitor.monitor import Monitor
    try:
        return Monitor(db).snapshot(), None
    except Exception as exc:
        log.warning("Monitoring snapshot alınamadı: %s", exc)
        return None, str(exc)


def get_events(db: Database, limit: int = 30):
    from manager.event_manager import EventManager
    try:
        return EventManager(db).list_events(limit=limit), None
    except Exception as exc:
        log.warning("Events okunamadı: %s", exc)
        return [], str(exc)


def get_policies(db: Database):
    from manager.policy_engine import PolicyEngine
    try:
        return {p.mac: p for p in PolicyEngine(db).evaluate_all()}, None
    except Exception as exc:
        return {}, str(exc)
