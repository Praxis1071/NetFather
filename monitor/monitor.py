"""
Canlı trafik monitoring katmanı.

Genel sistem TUI'si ``tui/`` altında mevcuttur. Bu modül gelecekte gerçek
trafik/cihaz telemetry akışını üretmek için ayrılmıştır.
"""

from __future__ import annotations

from core.database import Database


class Monitor:
    """Gelecekte canlı telemetry akışını yönetecek monitoring servisi."""

    def __init__(self, db: Database) -> None:
        self.db = db
