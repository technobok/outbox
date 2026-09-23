"""Schema migrations bring any database up to SCHEMA_VERSION."""

import threading

import apsw

from outbox.db import SCHEMA_VERSION, init_db_at, migrate, migrate_db_at
from tests.conftest import query


def _version(db_path: str) -> int:
    rows = query(db_path, "SELECT value FROM db_metadata WHERE key = 'schema_version'")
    return int(rows[0][0])


def _columns(db_path: str) -> list[str]:
    return [row[1] for row in query(db_path, "PRAGMA table_info(message)")]


def test_v1_database_is_migrated(v1_db_path: str) -> None:
    assert _version(v1_db_path) == 1
    assert "reply_to" not in _columns(v1_db_path)
    migrate_db_at(v1_db_path)
    assert _version(v1_db_path) == SCHEMA_VERSION == 2
    assert _columns(v1_db_path).count("reply_to") == 1


def test_migrate_is_repeatable(v1_db_path: str) -> None:
    migrate_db_at(v1_db_path)
    migrate_db_at(v1_db_path)
    assert _columns(v1_db_path).count("reply_to") == 1


def test_fresh_database_is_current(tmp_path) -> None:
    path = str(tmp_path / "outbox.sqlite3")
    init_db_at(path)
    assert _version(path) == SCHEMA_VERSION
    assert "reply_to" in _columns(path)
    # init-db on an existing database is still fine
    init_db_at(path)
    assert _columns(path).count("reply_to") == 1


def test_uninitialised_database_is_left_alone(tmp_path) -> None:
    path = str(tmp_path / "empty.sqlite3")
    conn = apsw.Connection(path)
    migrate(conn)
    assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []
    conn.close()


def test_concurrent_migrations(v1_db_path: str) -> None:
    errors: list[BaseException] = []

    def run() -> None:
        conn = apsw.Connection(v1_db_path)
        conn.execute("PRAGMA busy_timeout = 5000;")
        try:
            migrate(conn)
        except BaseException as e:
            errors.append(e)
        finally:
            conn.close()

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert _version(v1_db_path) == SCHEMA_VERSION


def test_app_startup_migrates(v1_db_path: str, monkeypatch) -> None:
    from outbox import create_app

    monkeypatch.setenv("OUTBOX_DB", v1_db_path)
    create_app()
    assert "reply_to" in _columns(v1_db_path)
