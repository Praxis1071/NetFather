"""
NetFather database bağlantı katmanı.

SQLite üzerinde SQLAlchemy engine ve session yönetimini sağlar.
Tüm modeller `models.base.Base` üzerinden bu engine'e bağlanır.

Tasarım notları:
    - SQLite varsayılan olarak foreign key kısıtlarını uygulamaz; bu modül
      her bağlantıda `PRAGMA foreign_keys=ON` çalıştırarak referans
      bütünlüğünü garanti eder.
    - `check_same_thread=False` farklı worker thread'lerinin aynı engine'i
      güvenle kullanabilmesini sağlar; gerçek eşzamanlılık SQLAlchemy'nin
      connection pool'u üzerinden yönetilir.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import DatabaseError
from core.logger import get_logger
from models.base import Base

log = get_logger("database")


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Her yeni DBAPI bağlantısında SQLite foreign key kısıtlarını açar."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Database:
    """SQLite database bağlantısını, şema kurulumunu ve session fabrikasını yönetir."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._is_new_database = not self.db_path.exists()

        try:
            self.engine = create_engine(
                f"sqlite:///{self.db_path}",
                connect_args={"check_same_thread": False},
                future=True,
            )
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Database engine oluşturulamadı: {exc}") from exc

        _enable_sqlite_foreign_keys(self.engine)
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )
        self._initialized = False

    def init_db(self) -> None:
        """Şemayı ve uyumlu ek sütunları idempotent biçimde oluşturur."""
        try:
            Base.metadata.create_all(self.engine)
            self._apply_compatible_migrations()
        except SQLAlchemyError as exc:
            raise DatabaseError(
                f"Database şeması oluşturulamadı ({self.db_path}): {exc}"
            ) from exc

        if not self._initialized:
            if self._is_new_database:
                log.info("Yeni database oluşturuldu: %s", self.db_path)
            else:
                log.info("Mevcut database yüklendi: %s", self.db_path)
        self._initialized = True

    def _apply_compatible_migrations(self) -> None:
        """Additive 0.x migrations that keep existing SQLite databases usable."""
        migrations = {
            "devices": {
                "hostname": "VARCHAR(255)",
                "os_hint": "VARCHAR(64)",
                "online": "BOOLEAN NOT NULL DEFAULT 0",
                "auto_registered": "BOOLEAN NOT NULL DEFAULT 0",
            },
            "events": {
                "device_mac": "VARCHAR(17)",
                "severity": "VARCHAR(16) NOT NULL DEFAULT 'info'",
                "metadata_json": "TEXT",
            },
        }
        with self.engine.begin() as connection:
            for table, columns in migrations.items():
                existing = {
                    row[1]
                    for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
                }
                for column, ddl in columns.items():
                    if column not in existing:
                        connection.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
                        )
                        log.info("Database migration: %s.%s eklendi", table, column)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Otomatik commit/rollback yapan bir SQLAlchemy session context manager."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise DatabaseError(f"Database işlemi başarısız oldu: {exc}") from exc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        """Engine'e ait tüm bağlantı havuzunu serbest bırakır."""
        self.engine.dispose()
        log.debug("Database bağlantısı kapatıldı: %s", self.db_path)


_db_instance: Database | None = None


def get_database(db_path: Path | None = None) -> Database:
    """Process genelindeki singleton Database örneğini döndürür."""
    global _db_instance
    if _db_instance is None:
        if db_path is None:
            raise DatabaseError("Database ilk kez başlatılırken db_path gereklidir.")
        _db_instance = Database(db_path)
        _db_instance.init_db()
    return _db_instance


def reset_database() -> None:
    """Singleton Database örneğini sıfırlar; testler için kullanılır."""
    global _db_instance
    if _db_instance is not None:
        _db_instance.close()
    _db_instance = None
