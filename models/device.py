"""Cihaz (Device) ORM modeli."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Device(Base):
    """Yerel ağda tespit edilmiş veya elle kaydedilmiş bir cihazı temsil eder."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    mac: Mapped[str] = mapped_column(String(17), unique=True, nullable=False, index=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_type: Mapped[str] = mapped_column(String(32), default="unknown")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )
    last_seen: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    profiles: Mapped[list["Profile"]] = relationship(  # noqa: F821
        back_populates="device", cascade="all, delete-orphan"
    )
    rules: Mapped[list["Rule"]] = relationship(  # noqa: F821
        back_populates="device", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug amaçlı
        return f"<Device id={self.id} name={self.name!r} mac={self.mac!r}>"
