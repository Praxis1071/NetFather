"""Linux GTK4 application configuration."""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.exceptions import ConfigError
from core.platform import apply_private_mode, default_config_dir, default_data_dir

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_DISCOVERY_MODES = {"passive", "active", "hybrid"}
DEFAULT_CONFIG_DIR = default_config_dir()
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_DATA_DIR = default_data_dir()
_DEFAULT_TOML = """[general]\napp_name = \"NetFather\"\ndata_dir = {data_dir}\n\n[database]\nfilename = \"netfather.db\"\n\n[logging]\nlevel = \"INFO\"\nfilename = \"netfather.log\"\nmax_bytes = 1048576\nbackup_count = 3\n\n[network]\nscan_timeout_seconds = 5\ndefault_interface = \"\"\n\n[discovery]\nmode = \"hybrid\"\ninterval_seconds = 15\nactive_timeout_seconds = 2\nsubnet = \"\"\nauto_register = true\nhostname_resolution = true\nvendor_detection = true\nos_detection = false\noffline_after_seconds = 45\n\n[firewall]\nbackend = \"auto\"\nenforcement_enabled = false\nrollback_on_error = true\n\n[monitor]\nrefresh_seconds = 3\n\n[daemon]\ninterval_seconds = 5\n"""

@dataclass
class GeneralConfig:
    app_name: str = "NetFather"
    data_dir: str = str(DEFAULT_DATA_DIR)

@dataclass
class DatabaseConfig:
    filename: str = "netfather.db"

@dataclass
class LoggingConfig:
    level: str = "INFO"
    filename: str = "netfather.log"
    max_bytes: int = 1_048_576
    backup_count: int = 3
    def __post_init__(self) -> None:
        self.level = self.level.upper()
        if self.level not in _VALID_LOG_LEVELS or self.max_bytes <= 0 or self.backup_count < 0:
            raise ConfigError("Geçersiz logging ayarları.")

@dataclass
class NetworkConfig:
    scan_timeout_seconds: int = 5
    default_interface: str = ""
    def __post_init__(self) -> None:
        if self.scan_timeout_seconds <= 0:
            raise ConfigError("network.scan_timeout_seconds pozitif olmalıdır.")

@dataclass
class DiscoveryConfig:
    mode: str = "hybrid"
    interval_seconds: int = 15
    active_timeout_seconds: int = 2
    subnet: str = ""
    auto_register: bool = True
    hostname_resolution: bool = True
    vendor_detection: bool = True
    os_detection: bool = False
    offline_after_seconds: int = 45
    def __post_init__(self) -> None:
        self.mode = self.mode.strip().lower()
        if self.mode not in _VALID_DISCOVERY_MODES or self.interval_seconds <= 0 or self.active_timeout_seconds <= 0:
            raise ConfigError("Geçersiz discovery ayarları.")
        if self.offline_after_seconds < self.interval_seconds:
            raise ConfigError("offline_after_seconds interval_seconds değerinden küçük olamaz.")

@dataclass
class FirewallConfig:
    backend: str = "auto"
    enforcement_enabled: bool = False
    rollback_on_error: bool = True
    def __post_init__(self) -> None:
        self.backend = self.backend.strip().lower()
        if self.backend not in {"auto", "nftables", "none"}:
            raise ConfigError("firewall.backend auto/nftables/none olmalıdır.")

@dataclass
class MonitorConfig:
    refresh_seconds: int = 3
    def __post_init__(self) -> None:
        if self.refresh_seconds <= 0:
            raise ConfigError("monitor.refresh_seconds pozitif olmalıdır.")

@dataclass
class DaemonConfig:
    interval_seconds: int = 5
    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ConfigError("daemon.interval_seconds pozitif olmalıdır.")

@dataclass
class Config:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    firewall: FirewallConfig = field(default_factory=FirewallConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    config_path: Path = DEFAULT_CONFIG_PATH
    @property
    def data_dir(self) -> Path: return Path(self.general.data_dir).expanduser()
    @property
    def database_path(self) -> Path: return self.data_dir / self.database.filename
    @property
    def log_path(self) -> Path: return self.data_dir / "logs" / self.logging.filename


def _ensure_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    apply_private_mode(path.parent, 0o700)
    if not path.exists():
        path.write_text(_DEFAULT_TOML.format(data_dir=json.dumps(str(DEFAULT_DATA_DIR))), encoding="utf-8")
        apply_private_mode(path, 0o600)


def _build_config(raw: dict[str, Any], path: Path) -> Config:
    try:
        return Config(general=GeneralConfig(**raw.get("general", {})), database=DatabaseConfig(**raw.get("database", {})), logging=LoggingConfig(**raw.get("logging", {})), network=NetworkConfig(**raw.get("network", {})), discovery=DiscoveryConfig(**raw.get("discovery", {})), firewall=FirewallConfig(**raw.get("firewall", {})), monitor=MonitorConfig(**raw.get("monitor", {})), daemon=DaemonConfig(**raw.get("daemon", {})), config_path=path)
    except TypeError as exc:
        raise ConfigError(f"Config dosyasında geçersiz alan: {exc}") from exc


def load_config(config_path: Path | None = None) -> Config:
    path = config_path or DEFAULT_CONFIG_PATH
    _ensure_default_config(path)
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Config dosyası okunamadı/geçersiz: {path}") from exc
    config = _build_config(raw, path)
    config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    apply_private_mode(config.data_dir, 0o700)
    (config.data_dir / "logs").mkdir(parents=True, exist_ok=True, mode=0o700)
    apply_private_mode(config.data_dir / "logs", 0o700)
    return config


def save_config(config: Config) -> None:
    d, f = config.discovery, config.firewall
    q = lambda value: json.dumps(str(value), ensure_ascii=False)
    b = lambda value: "true" if value else "false"
    content = f'''[general]\napp_name = {q(config.general.app_name)}\ndata_dir = {q(config.general.data_dir)}\n\n[database]\nfilename = {q(config.database.filename)}\n\n[logging]\nlevel = {q(config.logging.level)}\nfilename = {q(config.logging.filename)}\nmax_bytes = {config.logging.max_bytes}\nbackup_count = {config.logging.backup_count}\n\n[network]\nscan_timeout_seconds = {config.network.scan_timeout_seconds}\ndefault_interface = {q(config.network.default_interface)}\n\n[discovery]\nmode = {q(d.mode)}\ninterval_seconds = {d.interval_seconds}\nactive_timeout_seconds = {d.active_timeout_seconds}\nsubnet = {q(d.subnet)}\nauto_register = {b(d.auto_register)}\nhostname_resolution = {b(d.hostname_resolution)}\nvendor_detection = {b(d.vendor_detection)}\nos_detection = {b(d.os_detection)}\noffline_after_seconds = {d.offline_after_seconds}\n\n[firewall]\nbackend = {q(f.backend)}\nenforcement_enabled = {b(f.enforcement_enabled)}\nrollback_on_error = {b(f.rollback_on_error)}\n\n[monitor]\nrefresh_seconds = {config.monitor.refresh_seconds}\n\n[daemon]\ninterval_seconds = {config.daemon.interval_seconds}\n'''
    tmp = config.config_path.with_suffix(config.config_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    apply_private_mode(tmp, 0o600)
    tmp.replace(config.config_path)
    apply_private_mode(config.config_path, 0o600)
