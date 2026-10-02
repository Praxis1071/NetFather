"""Cihaz profili (Profile) ORM modeli."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Profile(Base):
    """Bir cihaza bağlı erişim profilini temsil eder (ör. 'Child Device')."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    internet_mode: Mapped[str] = mapped_column(
        String(32), default="unrestricted"
    )  # unrestricted | controlled | blocked

    device: Mapped["Device"] = relationship(back_populates="profiles")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Profile id={self.id} name={self.name!r} device_id={self.device_id}>"
