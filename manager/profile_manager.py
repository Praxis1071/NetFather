"""
Profile manager.

FAZ 1 kapsamında yalnızca modül iskeleti bulunur. Profil oluşturma,
atama ve internet modu yönetimi FAZ 4'te uygulanacaktır.
"""

from __future__ import annotations

from core.database import Database
from core.logger import get_logger

log = get_logger("profile_manager")


class ProfileManager:
    """Cihaz profillerini yönetir (FAZ 4'te tamamlanacak)."""

    def __init__(self, db: Database) -> None:
        self.db = db
