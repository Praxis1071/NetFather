"""
Zaman bazlı kural enforcement zamanlayıcısı.

Kural CRUD ve schedule değerlendirmesi ``manager.rule_manager`` içinde
mevcuttur. Bu modül ileride ayrıcalıklı firewall enforcement döngüsünü
çalıştırmak için ayrılmıştır.
"""

from __future__ import annotations

from core.database import Database


class RuleScheduler:
    """Gelecekte kuralları periyodik olarak uygulayacak enforcement servisi."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def start(self) -> None:
        """Enforcement scheduler henüz uygulanmadığı için açık hata verir."""
        raise NotImplementedError("Firewall enforcement scheduler henüz uygulanmamıştır.")
