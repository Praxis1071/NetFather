"""
NetFather logging kurulumu.

Rotating file handler ile dosyaya, ayrıca isteğe bağlı olarak konsola log
basan merkezi bir logger fabrikası sağlar.

Tasarım kararları:
    - Log dosyası, cihazlara ait MAC/IP gibi bilgiler içerebileceğinden
      0600 izniyle (yalnızca sahip kullanıcı okur/yazar) oluşturulur.
    - Log altyapısının kurulamaması (ör. disk dolu, izin hatası) CLI'nin
      çalışmasını engellememelidir; böyle bir durumda sessizce konsola
      (stderr) düşülür ve kullanıcı ham bir traceback ile karşılaşmaz.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import Config

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Log dosyası MAC/IP gibi hassas veriler içerebileceğinden yalnızca sahip
# kullanıcı tarafından okunabilir/yazılabilir olmalıdır.
_SECURE_FILE_MODE = 0o600

_configured = False


def _build_file_handler(log_path: Path, config: Config) -> RotatingFileHandler:
    """Rotating file handler'ı oluşturur ve dosyaya güvenli izin uygular."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=config.logging.max_bytes,
        backupCount=config.logging.backup_count,
        encoding="utf-8",
    )

    # Dosya bu noktada handler tarafından zaten oluşturulmuş olur.
    try:
        os.chmod(log_path, _SECURE_FILE_MODE)
    except OSError:
        # İzin değiştirilemese bile logging'i engellemeye değmez.
        pass

    return handler


def setup_logging(config: Config, console: bool = False) -> logging.Logger:
    """
    Kök NetFather logger'ını config'e göre kurar.

    Log dosyası oluşturulamazsa (izin, disk vb. sorunları) logging sessizce
    yalnızca konsola (stderr) düşer; bu durum CLI'nin çalışmasını engellemez.

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

    # LoggingConfig.__post_init__ zaten geçerli bir seviye garanti eder.
    logger.setLevel(getattr(logging, config.logging.level))
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    try:
        file_handler = _build_file_handler(config.log_path, config)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Dosyaya log yazılamıyorsa (ör. izin reddedildi) sessizce
        # konsola düş; kullanıcı CLI'yi normal şekilde kullanmaya devam
        # edebilmelidir.
        console = True

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


def reset_logging() -> None:
    """
    Logger kurulumunu sıfırlar.

    Yalnızca test senaryolarında, her testin logging'i kendi config'iyle
    yeniden kurabilmesi için kullanılır; normal CLI akışında çağrılmaz.
    """
    global _configured
    logger = logging.getLogger("netfather")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    _configured = False
