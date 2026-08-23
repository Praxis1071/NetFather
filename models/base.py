"""SQLAlchemy declarative base sınıfı. Tüm modeller buradan türer."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """NetFather ORM modelleri için ortak taban sınıf."""
