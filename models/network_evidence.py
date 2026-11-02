"""Persistent identity aliases and time-stamped address/service evidence."""
from __future__ import annotations

import datetime as dt
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
from core.time_utils import utc_now


class IdentityAlias(Base):
    __tablename__ = "identity_aliases"
    mac: Mapped[str] = mapped_column(String(17), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[dt.datetime] = mapped_column(default=utc_now)


class AddressEvidence(Base):
    __tablename__ = "address_evidence"
    __table_args__ = (UniqueConstraint("device_id", "ip", "interface"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    ip: Mapped[str] = mapped_column(String(45))
    interface: Mapped[str] = mapped_column(String(64), default="")
    observed_mac: Mapped[str] = mapped_column(String(17))
    source: Mapped[str] = mapped_column(String(64))
    first_seen: Mapped[dt.datetime] = mapped_column(default=utc_now)
    last_seen: Mapped[dt.datetime] = mapped_column(default=utc_now)


class ServiceEvidence(Base):
    __tablename__ = "service_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    ip: Mapped[str] = mapped_column(String(45))
    observed_at: Mapped[dt.datetime] = mapped_column(default=utc_now, index=True)
    tcp_ports: Mapped[str] = mapped_column(Text, default="[]")
    udp_ports: Mapped[str] = mapped_column(Text, default="[]")
    services: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(64), default="nmap")


class ScanRecord(Base):
    __tablename__ = "discovery_scans"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(default=utc_now)
    completed_at: Mapped[dt.datetime] = mapped_column(default=utc_now)
    mode: Mapped[str] = mapped_column(String(16))
    complete: Mapped[bool] = mapped_column(default=False)
    cancelled: Mapped[bool] = mapped_column(default=False)
    scanned: Mapped[int] = mapped_column(default=0)
    warnings: Mapped[str] = mapped_column(Text, default="[]")
