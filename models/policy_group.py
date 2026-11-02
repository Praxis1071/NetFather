"""Reusable policy profiles; legacy device-bound profiles stay readable."""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base


class PolicyGroup(Base):
    __tablename__ = "policy_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    internet_mode: Mapped[str] = mapped_column(String(32), default="controlled")


class ProfileAssignment(Base):
    __tablename__ = "profile_assignments"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("policy_groups.id", ondelete="RESTRICT"), index=True)


class GroupRule(Base):
    __tablename__ = "group_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("policy_groups.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(16), default="block")
    schedule: Mapped[str] = mapped_column(String(512))
    enabled: Mapped[bool] = mapped_column(default=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    priority: Mapped[int] = mapped_column(default=0)
    timezone: Mapped[str] = mapped_column(String(128), default="local")
    weekdays: Mapped[str] = mapped_column(String(16), default="0,1,2,3,4,5,6")
