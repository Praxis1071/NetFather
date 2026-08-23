"""NetFather CLI çalıştırma noktası."""

from __future__ import annotations

import sys

from cli.commands import app
from cli.output import print_error
from core.logger import get_logger

log = get_logger("cli")


def run() -> None:
    """
    Typer uygulamasını başlatır.

    Typer/Click'in normal kontrollü çıkışları (`--help`, doğrulanmış
    argüman hataları, `typer.Exit`) burada müdahale edilmeden olduğu gibi
    dışarı verilir. Öngörülmeyen (beklenmeyen) hatalar ise kullanıcıya ham
    bir Python traceback'i olarak değil, kısa ve anlaşılır bir mesajla
    gösterilir; ayrıntı log dosyasına yazılır.
    """
    try:
        app()
    except KeyboardInterrupt:
        print_error("İşlem kullanıcı tarafından iptal edildi.")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - son çare güvenlik ağı
        log.exception("Beklenmeyen hata: %s", exc)
        print_error(
            "Beklenmeyen bir hata oluştu. Ayrıntılar log dosyasına kaydedildi."
        )
        sys.exit(1)


if __name__ == "__main__":
    run()
