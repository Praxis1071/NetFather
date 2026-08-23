"""Cihaz (Device) ORM modeli."""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from models.base import Base

# Girişte ':' veya '-' ayraçlı kabul edilir; normalize sonrası her zaman ':' kullanılır.
_MAC_INPUT_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


class Device(Base):
    """Yerel ağda tespit edilmiş veya elle kaydedilmiş bir cihazı temsil eder."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
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

    @validates("mac")
    def _validate_mac(self, _key: str, value: str) -> str:
        """MAC adresini doğrular ve saklama öncesi 'AA:BB:CC:DD:EE:FF' formuna normalize eder."""
        candidate = value.strip()
        if not _MAC_INPUT_PATTERN.match(candidate):
            raise ValueError(f"Geçersiz MAC adresi formatı: {value!r}")
        return candidate.upper().replace("-", ":")

    @validates("name")
    def _validate_name(self, _key: str, value: str) -> str:
        """Cihaz isminin boş olmamasını garanti eder ve kenar boşluklarını temizler."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Cihaz ismi boş olamaz.")
        return cleaned

    def __repr__(self) -> str:  # pragma: no cover - debug amaçlı
        return f"<Device id={self.id} name={self.name!r} mac={self.mac!r}>"
