"""core.database.Database için testler: şema kurulumu ve session davranışı."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect

from core.database import Database
from models.device import Device

EXPECTED_TABLES = {"devices", "profiles", "rules", "events"}


@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "netfather-test.db")
    database.init_db()
    yield database
    database.close()


def test_init_db_creates_database_file(tmp_path: Path) -> None:
    db_path = tmp_path / "netfather-test.db"
    assert not db_path.exists()

    database = Database(db_path)
    database.init_db()

    assert db_path.exists()
    database.close()


def test_init_db_creates_expected_tables(db: Database) -> None:
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES <= tables


def test_init_db_is_idempotent(db: Database) -> None:
    # İkinci çağrı hata fırlatmamalı ve tabloları bozmamalı.
    db.init_db()
    inspector = inspect(db.engine)
    assert EXPECTED_TABLES <= set(inspector.get_table_names())


def test_session_commits_on_success(db: Database) -> None:
    with db.session() as session:
        session.add(Device(name="Laptop", mac="AA:BB:CC:DD:EE:01"))

    with db.session() as session:
        count = session.query(Device).count()
    assert count == 1


def test_session_rolls_back_on_error(db: Database) -> None:
    with pytest.raises(RuntimeError):
        with db.session() as session:
            session.add(Device(name="Laptop", mac="AA:BB:CC:DD:EE:02"))
            raise RuntimeError("kasıtlı test hatası")

    with db.session() as session:
        count = session.query(Device).count()
    assert count == 0
