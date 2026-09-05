"""NetFather cross-platform configuration management."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from core.exceptions import ConfigError
from core.platform import apply_private_mode, default_config_dir, default_data_dir

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_DISCOVERY_MODES = {"passive", "active", "hybrid"}
_SECURE_DIR_MODE = 0o700

DEFAULT_CONFIG_DIR = default_config_dir()
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_DATA_DIR = default_data_dir()

DEFAULT_CONFIG_TOML = """\
[general]
app_name = "NetFather"
data_dir = {data_dir}

[database]
filename = "netfather.db"

[logging]
level = "INFO"
filename = "netfather.log"
max_bytes = 1048576
backup_count = 3

[network]
scan_timeout_seconds = 5
default_interface = ""

[discovery]
mode = "hybrid"
interval_seconds = 15
active_timeout_seconds = 2
subnet = ""
auto_register = true
hostname_resolution = true
vendor_detection = true
os_detection = false
offline_after_seconds = 45

[firewall]
backend = "auto"
enforcement_enabled = false
rollback_on_error = true

[monitor]
refresh_seconds = 3

[daemon]
interval_seconds = 5
"""


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
        if self.level not in _VALID_LOG_LEVELS:
            raise ConfigError(
                f"Geçersiz log seviyesi: {self.level!r}. "
                f"Geçerli değerler: {', '.join(sorted(_VALID_LOG_LEVELS))}"
            )
        if self.max_bytes <= 0:
            raise ConfigError("logging.max_bytes pozitif bir tam sayı olmalıdır.")
        if self.backup_count < 0:
            raise ConfigError("logging.backup_count negatif olamaz.")


@dataclass
class NetworkConfig:
    scan_timeout_seconds: int = 5
    default_interface: str = ""

    def __post_init__(self) -> None:
        if self.scan_timeout_seconds <= 0:
            raise ConfigError("network.scan_timeout_seconds pozitif olmalıdır.")


@dataclass
class DiscoveryConfig:
    """Discovery and live-presence settings."""

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
        if self.mode not in _VALID_DISCOVERY_MODES:
            raise ConfigError("discovery.mode passive, active veya hybrid olmalıdır.")
        if self.interval_seconds <= 0:
            raise ConfigError("discovery.interval_seconds pozitif olmalıdır.")
        if self.active_timeout_seconds <= 0:
            raise ConfigError("discovery.active_timeout_seconds pozitif olmalıdır.")
        if self.offline_after_seconds < self.interval_seconds:
            raise ConfigError(
                "discovery.offline_after_seconds interval_seconds değerinden küçük olamaz."
            )


@dataclass
class FirewallConfig:
    backend: str = "auto"
    enforcement_enabled: bool = False
    rollback_on_error: bool = True

    def __post_init__(self) -> None:
        self.backend = self.backend.strip().lower()
        if self.backend not in {"auto", "nftables", "windows", "pf", "none"}:
            raise ConfigError("firewall.backend auto/nftables/windows/pf/none olmalıdır.")


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
    def data_dir(self) -> Path:
        return Path(self.general.data_dir).expanduser()

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database.filename

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs" / self.logging.filename


def _ensure_default_config(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=_SECURE_DIR_MODE)
    apply_private_mode(config_path.parent, _SECURE_DIR_MODE)
    if not config_path.exists():
        content = DEFAULT_CONFIG_TOML.format(data_dir=json.dumps(str(DEFAULT_DATA_DIR)))
        config_path.write_text(content, encoding="utf-8")
        apply_private_mode(config_path, 0o600)


def _build_config(raw: dict[str, Any], config_path: Path) -> Config:
    try:
        return Config(
            general=GeneralConfig(**raw.get("general", {})),
            database=DatabaseConfig(**raw.get("database", {})),
            logging=LoggingConfig(**raw.get("logging", {})),
            network=NetworkConfig(**raw.get("network", {})),
            discovery=DiscoveryConfig(**raw.get("discovery", {})),
            firewall=FirewallConfig(**raw.get("firewall", {})),
            monitor=MonitorConfig(**raw.get("monitor", {})),
            daemon=DaemonConfig(**raw.get("daemon", {})),
            config_path=config_path,
        )
    except TypeError as exc:
        raise ConfigError(f"Config dosyasında geçersiz alan bulundu: {exc}") from exc


def load_config(config_path: Path | None = None) -> Config:
    """Load config, creating a platform-native default file when necessary."""
    path = config_path or DEFAULT_CONFIG_PATH
    _ensure_default_config(path)
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except OSError as exc:
        raise ConfigError(f"Config dosyası okunamadı ({path}): {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config dosyası geçersiz TOML içeriyor ({path}): {exc}") from exc

    config = _build_config(raw, path)
    config.data_dir.mkdir(parents=True, exist_ok=True, mode=_SECURE_DIR_MODE)
    apply_private_mode(config.data_dir, _SECURE_DIR_MODE)
    (config.data_dir / "logs").mkdir(parents=True, exist_ok=True, mode=_SECURE_DIR_MODE)
    apply_private_mode(config.data_dir / "logs", _SECURE_DIR_MODE)
    return config


def save_config(config: Config) -> None:
    """Persist the complete current configuration atomically as valid TOML."""
    def q(value: str) -> str:
        return json.dumps(str(value), ensure_ascii=False)
    def b(value: bool) -> str:
        return "true" if value else "false"
    d, f = config.discovery, config.firewall
    content = f'''[general]\napp_name = {q(config.general.app_name)}\ndata_dir = {q(config.general.data_dir)}\n\n[database]\nfilename = {q(config.database.filename)}\n\n[logging]\nlevel = {q(config.logging.level)}\nfilename = {q(config.logging.filename)}\nmax_bytes = {config.logging.max_bytes}\nbackup_count = {config.logging.backup_count}\n\n[network]\nscan_timeout_seconds = {config.network.scan_timeout_seconds}\ndefault_interface = {q(config.network.default_interface)}\n\n[discovery]\nmode = {q(d.mode)}\ninterval_seconds = {d.interval_seconds}\nactive_timeout_seconds = {d.active_timeout_seconds}\nsubnet = {q(d.subnet)}\nauto_register = {b(d.auto_register)}\nhostname_resolution = {b(d.hostname_resolution)}\nvendor_detection = {b(d.vendor_detection)}\nos_detection = {b(d.os_detection)}\noffline_after_seconds = {d.offline_after_seconds}\n\n[firewall]\nbackend = {q(f.backend)}\nenforcement_enabled = {b(f.enforcement_enabled)}\nrollback_on_error = {b(f.rollback_on_error)}\n\n[monitor]\nrefresh_seconds = {config.monitor.refresh_seconds}\n\n[daemon]\ninterval_seconds = {config.daemon.interval_seconds}\n'''
    tmp = config.config_path.with_suffix(config.config_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    apply_private_mode(tmp, 0o600)
    tmp.replace(config.config_path)
    apply_private_mode(config.config_path, 0o600)
