"""Olay kaydı (Event) ORM modeli. Monitoring ve geçmiş takibi için kullanılır."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Event(Base):
    """Sistem içinde oluşan olayları kaydeder (cihaz görüldü, kural tetiklendi vb.)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Event id={self.id} type={self.event_type!r}>"
