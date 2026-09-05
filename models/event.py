"""Audit/event model."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.time_utils import utc_now
from models.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=utc_now)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    device_mac: Mapped[str | None] = mapped_column(String(17), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Event id={self.id} type={self.event_type!r}>"
