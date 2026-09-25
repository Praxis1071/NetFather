"""core.database.Database için testler: şema kurulumu ve session davranışı."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect

from core.database import Database
from models.device import Device

EXPECTED_TABLES = {"devices", "device_observations", "profiles", "rules", "events"}


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


def test_init_db_applies_additive_migrations_to_legacy_database(tmp_path: Path) -> None:
    import sqlite3

    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE devices (
                id INTEGER PRIMARY KEY,
                name VARCHAR(128) NOT NULL UNIQUE,
                mac VARCHAR(17) NOT NULL UNIQUE,
                ip VARCHAR(45),
                vendor VARCHAR(128),
                device_type VARCHAR(32)
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                timestamp DATETIME,
                event_type VARCHAR(32) NOT NULL,
                description VARCHAR(512) NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    database = Database(db_path)
    database.init_db()
    inspector = inspect(database.engine)

    device_columns = {column["name"] for column in inspector.get_columns("devices")}
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    assert {"hostname", "os_hint", "online", "auto_registered"} <= device_columns
    assert {"device_mac", "severity", "metadata_json"} <= event_columns
    assert "device_observations" in inspector.get_table_names()
    database.close()
