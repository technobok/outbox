"""Shared fixtures: every test gets its own database in a tmp directory."""

from pathlib import Path
from types import SimpleNamespace

import apsw
import pytest
from flask import Flask, g
from flask.testing import FlaskClient

from outbox import create_app
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


@pytest.fixture
def app(db_path: str, monkeypatch: pytest.MonkeyPatch) -> Flask:
    """The Flask app on db_path, with a logged-in admin user."""
    monkeypatch.delenv("OUTBOX_DB", raising=False)
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE_PATH": db_path,
            "BLOB_DIRECTORY": "blobs",
            "BLOB_MAX_SIZE_MB": 1,
            "QUEUE_MAX_RETRIES": 5,
        }
    )

    @app.before_request
    def _login() -> None:
        g.user = SimpleNamespace(username="tester")

    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def api_key(app: Flask) -> str:
    from outbox.models.api_key import ApiKey

    with app.app_context():
        return ApiKey.generate(description="test").key
