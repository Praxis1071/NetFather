"""
Rule manager.

FAZ 1 kapsamında yalnızca modül iskeleti bulunur. Zaman bazlı erişim
kurallarının oluşturulması ve uygulanması FAZ 5'te eklenecektir.
"""

from __future__ import annotations

from core.database import Database
from core.logger import get_logger

log = get_logger("rule_manager")


class RuleManager:
    """Cihaz bazlı erişim kurallarını yönetir (FAZ 5'te tamamlanacak)."""

    def __init__(self, db: Database) -> None:
        self.db = db
