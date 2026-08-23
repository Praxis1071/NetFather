"""
Canlı monitoring ekranı.

FAZ 1 kapsamında yalnızca modül iskeleti bulunur. Rich tabanlı canlı
terminal görünümü FAZ 6'da uygulanacaktır.
"""

from __future__ import annotations

from core.database import Database


class Monitor:
    """Canlı cihaz durumu görünümünü yönetir (FAZ 6'da tamamlanacak)."""

    def __init__(self, db: Database) -> None:
        self.db = db
