"""Database connection and transaction handling using APSW."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import apsw

_standalone_db: apsw.Connection | None = None


def get_db_path() -> str:
    """Resolve the database path.

    Priority:
      1. OUTBOX_DB environment variable
      2. Flask current_app.config["DATABASE_PATH"] (if in app context)
      3. instance/outbox.sqlite3 relative to project root (fallback)
    """
    import os

    db_path = os.environ.get("OUTBOX_DB")
    if db_path:
        return db_path

    try:
        from flask import current_app

        return current_app.config["DATABASE_PATH"]
    except RuntimeError, KeyError:
        pass

    source_root = Path(__file__).parent.parent.parent
    return str(source_root / "instance" / "outbox.sqlite3")


def _configure_connection(conn: apsw.Connection) -> None:
    """Apply standard PRAGMAs to a connection."""
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")


def get_db() -> apsw.Connection:
    """Get the database connection for the current request (Flask context)."""
    from flask import g

    if "db" not in g:
        db_path = get_db_path()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        g.db = apsw.Connection(db_path)
        _configure_connection(g.db)
    return g.db


def close_db(e: BaseException | None = None) -> None:
    """Close the database connection at the end of the request."""
    from flask import g

    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Standalone DB access (no Flask context required)
# ---------------------------------------------------------------------------


def get_standalone_db() -> apsw.Connection:
    """Get a database connection without Flask context.

    Used by CLI commands that don't need the full Flask app.
    The connection is cached at module level.
    """
    global _standalone_db
    if _standalone_db is None:
        db_path = get_db_path()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _standalone_db = apsw.Connection(db_path)
        _configure_connection(_standalone_db)
    return _standalone_db


def close_standalone_db() -> None:
    """Close the standalone database connection."""
    global _standalone_db
    if _standalone_db is not None:
        _standalone_db.close()
        _standalone_db = None


@contextmanager
def standalone_transaction() -> Generator[apsw.Cursor]:
    """Transaction context manager for standalone (non-Flask) DB access."""
    db = get_standalone_db()
    cursor = db.cursor()
    cursor.execute("BEGIN IMMEDIATE;")
    try:
        yield cursor
        cursor.execute("COMMIT;")
    except Exception:
        cursor.execute("ROLLBACK;")
        raise


# ---------------------------------------------------------------------------
# Flask-context transactions
# ---------------------------------------------------------------------------


@contextmanager
def transaction() -> Generator[apsw.Cursor]:
    """Context manager for database transactions.

    Automatically commits on success, rolls back on exception.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("BEGIN IMMEDIATE;")
    try:
        yield cursor
        cursor.execute("COMMIT;")
    except Exception:
        cursor.execute("ROLLBACK;")
        raise


@contextmanager
def in_transaction(cursor: apsw.Cursor | None) -> Generator[apsw.Cursor]:
    """Join the caller's transaction when given its cursor, else open one."""
    if cursor is not None:
        yield cursor
        return
    with transaction() as own:
        yield own


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def init_db_at(db_path: str) -> None:
    """Initialize the database schema at the given path.

    Works without Flask context.
    """
    import secrets

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = apsw.Connection(db_path)
    _configure_connection(conn)

    schema_path = Path(__file__).parent.parent.parent / "database" / "schema.sql"
    with open(schema_path) as f:
        for _ in conn.execute(f.read()):
            pass

    # Generate secret_key if not exists
    row = conn.execute("SELECT value FROM app_setting WHERE key = 'secret_key'").fetchone()
    if not row:
        new_key = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT OR IGNORE INTO app_setting (key, value, description) VALUES (?, ?, ?)",
            ("secret_key", new_key, "Secret key for signing auth tokens"),
        )

    migrate(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------
#
# database/schema.sql is the version 1 baseline and is never edited. Every
# later change is a step here, and migrate() brings any database - fresh from
# init-db or years old - up to SCHEMA_VERSION. It runs wherever the database is
# opened for writing: create_app (web, worker, CLI), init-db, and the client's
# LocalBackend, which writes into this database from another application and
# so may reach it before the outbox server has been restarted.

SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, Callable[[apsw.Cursor], None]] = {}


def _read_schema_version(cursor: apsw.Cursor) -> int | None:
    """The recorded schema version, or None for an uninitialised database."""
    try:
        row = cursor.execute(
            "SELECT value FROM db_metadata WHERE key = 'schema_version'"
        ).fetchone()
    except apsw.SQLError:
        return None
    return int(str(row[0])) if row else None


def migrate(conn: apsw.Connection) -> None:
    """Apply any schema migrations the database has not yet had.

    A database with no db_metadata table has not been initialised; that is
    init-db's job, so it is left alone.
    """
    cursor = conn.cursor()
    version = _read_schema_version(cursor)
    if version is None or version >= SCHEMA_VERSION:
        return

    # web, worker and LocalBackend clients can all start at once: take the
    # write lock, then read the version again - another process may have
    # migrated in between.
    cursor.execute("BEGIN IMMEDIATE;")
    try:
        version = _read_schema_version(cursor)
        if version is not None and version < SCHEMA_VERSION:
            for step in range(version + 1, SCHEMA_VERSION + 1):
                _MIGRATIONS[step](cursor)
            cursor.execute(
                "UPDATE db_metadata SET value = ? WHERE key = 'schema_version'",
                (str(SCHEMA_VERSION),),
            )
        cursor.execute("COMMIT;")
    except Exception:
        cursor.execute("ROLLBACK;")
        raise


def migrate_db_at(db_path: str) -> None:
    """Migrate the database at db_path, if one exists there.

    A missing file means init-db hasn't been run; it migrates what it creates.
    """
    if not Path(db_path).exists():
        return
    conn = apsw.Connection(db_path)
    try:
        _configure_connection(conn)
        migrate(conn)
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database with the schema (Flask context)."""
    db_path = get_db_path()
    init_db_at(db_path)


def get_schema_version() -> int:
    """Get the current schema version from db_metadata."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT value FROM db_metadata WHERE key = 'schema_version'")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except apsw.SQLError:
        return 0
