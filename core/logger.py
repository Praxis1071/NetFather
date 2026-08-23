"""
NetFather logging kurulumu.

Rotating file handler ile dosyaya, ayrıca isteğe bağlı olarak
konsola log basan merkezi bir logger fabrikası sağlar.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import Config

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(config: Config, console: bool = False) -> logging.Logger:
    """
    Kök NetFather logger'ını config'e göre kurar.

    Args:
        config: Yüklenmiş Config nesnesi.
        console: True ise konsola da log basılır (varsayılan kapalı,
            çünkü CLI çıktısı Rich üzerinden ayrıca yönetiliyor).

    Returns:
        Kurulmuş "netfather" logger'ı.
    """
    global _configured

    logger = logging.getLogger("netfather")

    if _configured:
        return logger

    log_path: Path = config.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=config.logging.max_bytes,
        backupCount=config.logging.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.propagate = False
    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Verilen isimle 'netfather' altında bir alt logger döndürür."""
    return logging.getLogger(f"netfather.{name}")
