"""Persistent network observations used to preserve device identity history."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.time_utils import utc_now
from models.base import Base


class DeviceObservationRecord(Base):
    """Historical observation of a managed device on the local network."""

    __tablename__ = "device_observations"
    __table_args__ = (
        Index("ix_device_observations_device_observed_at", "device_id", "observed_at"),
        Index("ix_device_observations_device_ip", "device_id", "ip"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    interface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    os_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    device: Mapped["Device"] = relationship(back_populates="observations")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DeviceObservationRecord id={self.id} device_id={self.device_id} ip={self.ip!r}>"
