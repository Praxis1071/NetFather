"""
NetFather config yönetimi.

Uygulama ayarları TOML formatında ~/.config/netfather/config.toml
dosyasında tutulur. Dosya yoksa varsayılan değerlerle otomatik oluşturulur.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.12+ hedeflendiği için normalde kullanılmaz
    import tomli as tomllib  # type: ignore[no-redef]

from core.exceptions import ConfigError

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "netfather"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "netfather"

DEFAULT_CONFIG_TOML = """\
[general]
app_name = "NetFather"
data_dir = "{data_dir}"

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

[monitor]
refresh_seconds = 3
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


@dataclass
class NetworkConfig:
    scan_timeout_seconds: int = 5
    default_interface: str = ""


@dataclass
class MonitorConfig:
    refresh_seconds: int = 3


@dataclass
class Config:
    """NetFather'ın tüm ayarlarını tutan üst seviye config nesnesi."""

    general: GeneralConfig = field(default_factory=GeneralConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    config_path: Path = DEFAULT_CONFIG_PATH

    @property
    def data_dir(self) -> Path:
        path = Path(self.general.data_dir).expanduser()
        return path

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database.filename

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs" / self.logging.filename


def _ensure_default_config(config_path: Path) -> None:
    """Config dosyası yoksa varsayılan içerikle oluşturur."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        content = DEFAULT_CONFIG_TOML.format(data_dir=str(DEFAULT_DATA_DIR))
        config_path.write_text(content, encoding="utf-8")


def _build_config(raw: dict[str, Any], config_path: Path) -> Config:
    try:
        general = GeneralConfig(**raw.get("general", {}))
        database = DatabaseConfig(**raw.get("database", {}))
        logging_cfg = LoggingConfig(**raw.get("logging", {}))
        network = NetworkConfig(**raw.get("network", {}))
        monitor = MonitorConfig(**raw.get("monitor", {}))
    except TypeError as exc:
        raise ConfigError(f"Config dosyasında geçersiz alan bulundu: {exc}") from exc

    return Config(
        general=general,
        database=database,
        logging=logging_cfg,
        network=network,
        monitor=monitor,
        config_path=config_path,
    )


def load_config(config_path: Path | None = None) -> Config:
    """
    Config dosyasını yükler. Dosya yoksa varsayılan değerlerle oluşturur.

    Args:
        config_path: Alternatif bir config dosyası yolu. Verilmezse
            varsayılan kullanıcı config dizini kullanılır.

    Returns:
        Doldurulmuş Config nesnesi.
    """
    path = config_path or DEFAULT_CONFIG_PATH
    _ensure_default_config(path)

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Config dosyası okunamadı ({path}): {exc}") from exc

    config = _build_config(raw, path)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / "logs").mkdir(parents=True, exist_ok=True)
    return config
