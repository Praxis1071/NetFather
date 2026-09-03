"""
NetFather config yönetimi.

Uygulama ayarları TOML formatında saklanır ve XDG Base Directory
Specification'a uyar:

    - Config dosyası : $XDG_CONFIG_HOME/netfather/config.toml
                        (varsayılan: ~/.config/netfather/config.toml)
    - Veri dizini     : $XDG_DATA_HOME/netfather/
                        (varsayılan: ~/.local/share/netfather/)

Config dosyası veya üst dizinleri yoksa ilk çalıştırmada otomatik olarak
güvenli izinlerle (0700) oluşturulur.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - proje 3.12+ hedefler, bu dal normalde çalışmaz
    import tomli as tomllib  # type: ignore[no-redef]

from core.exceptions import ConfigError

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# Dizinler için güvenli izin: yalnızca sahip kullanıcı okuyabilir/yazabilir.
# NetFather ağdaki cihazların MAC/IP bilgilerini sakladığı için bu veri
# dizinlerinin diğer sistem kullanıcılarına kapalı olması gerekir.
_SECURE_DIR_MODE = 0o700


def _xdg_config_home() -> Path:
    """XDG_CONFIG_HOME ortam değişkenini, tanımlı değilse ~/.config'i döndürür."""
    value = os.environ.get("XDG_CONFIG_HOME")
    if value:
        return Path(value).expanduser()
    return Path.home() / ".config"


def _xdg_data_home() -> Path:
    """XDG_DATA_HOME ortam değişkenini, tanımlı değilse ~/.local/share'i döndürür."""
    value = os.environ.get("XDG_DATA_HOME")
    if value:
        return Path(value).expanduser()
    return Path.home() / ".local" / "share"


DEFAULT_CONFIG_DIR = _xdg_config_home() / "netfather"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_DATA_DIR = _xdg_data_home() / "netfather"

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
class MonitorConfig:
    refresh_seconds: int = 3

    def __post_init__(self) -> None:
        if self.refresh_seconds <= 0:
            raise ConfigError("monitor.refresh_seconds pozitif olmalıdır.")


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
        return Path(self.general.data_dir).expanduser()

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database.filename

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs" / self.logging.filename


def _ensure_default_config(config_path: Path) -> None:
    """Config dosyası yoksa güvenli izinlerle ve varsayılan içerikle oluşturur."""
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=_SECURE_DIR_MODE)
    os.chmod(config_path.parent, _SECURE_DIR_MODE)

    if not config_path.exists():
        content = DEFAULT_CONFIG_TOML.format(data_dir=str(DEFAULT_DATA_DIR))
        config_path.write_text(content, encoding="utf-8")
        os.chmod(config_path, 0o600)


def _build_config(raw: dict[str, Any], config_path: Path) -> Config:
    """Ham TOML sözlüğünden tip güvenli bir Config nesnesi üretir."""
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

    İlk çağrıda config dizini ve veri dizini yoksa oluşturulur (0700 izinle),
    çünkü NetFather ağdaki cihazlara ait MAC/IP gibi bilgileri saklar ve bu
    verinin diğer sistem kullanıcılarınca okunabilir olmaması gerekir.

    Args:
        config_path: Alternatif bir config dosyası yolu. Verilmezse
            XDG_CONFIG_HOME (veya ~/.config) altındaki varsayılan yol
            kullanılır.

    Returns:
        Doldurulmuş ve doğrulanmış Config nesnesi.

    Raises:
        ConfigError: Dosya okunamazsa, bozuksa veya alan değerleri
            geçersizse.
    """
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
    os.chmod(config.data_dir, _SECURE_DIR_MODE)
    (config.data_dir / "logs").mkdir(parents=True, exist_ok=True, mode=_SECURE_DIR_MODE)
    os.chmod(config.data_dir / "logs", _SECURE_DIR_MODE)

    return config
