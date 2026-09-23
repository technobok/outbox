"""Shared fixtures: every test gets its own database in a tmp directory."""

from pathlib import Path

import apsw
import pytest

from outbox.db import init_db_at


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """An initialised, fully migrated database."""
    path = str(tmp_path / "instance" / "outbox.sqlite3")
    init_db_at(path)
    return path


@pytest.fixture
def v1_db_path(tmp_path: Path) -> str:
    """A database built from the version 1 baseline only, as older installs have."""
    path = tmp_path / "instance" / "outbox.sqlite3"
    path.parent.mkdir(parents=True)
    schema = Path(__file__).parent.parent / "database" / "schema.sql"
    conn = apsw.Connection(str(path))
    for _ in conn.execute(schema.read_text()):
        pass
    conn.close()
    return str(path)


def query(db_path: str, sql: str, params: tuple = ()) -> list[tuple]:
    conn = apsw.Connection(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()
