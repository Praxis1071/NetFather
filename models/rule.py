"""Erişim kuralı (Rule) ORM modeli."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Rule(Base):
    """
    Bir cihaza uygulanan zaman bazlı erişim kuralını temsil eder.

    schedule alanı noktalı virgülle ayrılmış "HH:MM-HH:MM" aralıkları içerir.
    timezone IANA bölgesini, weekdays başlangıç günlerini (0=Pazartesi) tutar.
    action alanı "block" veya "allow" değerini alır.
    """

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(16), default="block")
    schedule: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    priority: Mapped[int] = mapped_column(default=0)
    timezone: Mapped[str] = mapped_column(String(128), default="local")
    weekdays: Mapped[str] = mapped_column(String(16), default="0,1,2,3,4,5,6")

    device: Mapped["Device"] = relationship(back_populates="rules")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Rule id={self.id} device_id={self.device_id} schedule={self.schedule!r}>"
