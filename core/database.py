"""
NetFather database bağlantı katmanı.

SQLite üzerinde SQLAlchemy engine ve session yönetimini sağlar.
Tüm modeller `models.base.Base` üzerinden bu engine'e bağlanır.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import DatabaseError
from core.logger import get_logger
from models.base import Base

log = get_logger("database")


class Database:
    """SQLite database bağlantısını ve session fabrikasını yönetir."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.engine = create_engine(
                f"sqlite:///{self.db_path}",
                connect_args={"check_same_thread": False},
                future=True,
            )
        except Exception as exc:  # noqa: BLE001 - engine oluşturma hatası sarmalanıyor
            raise DatabaseError(f"Database engine oluşturulamadı: {exc}") from exc

        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    def init_db(self) -> None:
        """Tüm tabloları (yoksa) oluşturur."""
        try:
            Base.metadata.create_all(self.engine)
            log.info("Database tabloları hazır: %s", self.db_path)
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(f"Tablolar oluşturulamadı: {exc}") from exc

    @contextmanager
    def session(self) -> Iterator[Session]:
        """
        Otomatik commit/rollback yapan bir session context manager'ı.

        Kullanım:
            with db.session() as session:
                session.add(obj)
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_db_instance: Database | None = None


def get_database(db_path: Path | None = None) -> Database:
    """
    Singleton Database örneğini döndürür. İlk çağrıda db_path zorunludur.
    """
    global _db_instance
    if _db_instance is None:
        if db_path is None:
            raise DatabaseError("Database ilk kez başlatılırken db_path gereklidir.")
        _db_instance = Database(db_path)
        _db_instance.init_db()
    return _db_instance
