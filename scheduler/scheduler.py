"""
Zaman bazlı kural zamanlayıcısı.

FAZ 1 kapsamında yalnızca modül iskeleti bulunur. APScheduler tabanlı
periyodik kural değerlendirmesi FAZ 5'te uygulanacaktır.
"""

from __future__ import annotations

from core.database import Database


class RuleScheduler:
    """Kuralları periyodik olarak değerlendirip uygular (FAZ 5'te tamamlanacak)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def start(self) -> None:
        """Zamanlayıcıyı başlatır (FAZ 5)."""
        raise NotImplementedError("Scheduler FAZ 5'te uygulanacaktır.")
