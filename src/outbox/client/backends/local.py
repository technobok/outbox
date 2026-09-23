"""Local SQLite backend for OutboxClient (direct DB insertion)."""

import json
import uuid as uuid_mod
from datetime import UTC, datetime
from pathlib import Path

import apsw

from outbox.blobs import resolve_blob_dir, store_blob
from outbox.client.models import Message, MessageResult
from outbox.config import resolve_entry, serialize_value
from outbox.db import migrate

# Databases already migrated by this process. A client is often built per
# message, so this keeps it to one version check per database, not per send.
_migrated: set[str] = set()


def _opt_str(val: object) -> str | None:
    return str(val) if val is not None else None


def _result_from_row(row: tuple) -> MessageResult:
    return MessageResult(
        uuid=str(row[0]),
        status=str(row[1]),
        created_at=_opt_str(row[2]),
        updated_at=_opt_str(row[3]),
        sent_at=_opt_str(row[4]),
        last_error=_opt_str(row[5]),
    )


class LocalBackend:
    """Backend that inserts directly into the Outbox SQLite database."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _connect(self) -> apsw.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = apsw.Connection(self.db_path)
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        if self.db_path not in _migrated:
            # this client may be newer than the outbox server that owns the
            # database, and reach it before the server has been restarted
            migrate(conn)
            _migrated.add(self.db_path)
        return conn

    def _setting(self, conn: apsw.Connection, key: str) -> str:
        """The effective raw value of a setting, as the outbox server would see it."""
        entry = resolve_entry(key)
        assert entry is not None, key
        row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else serialize_value(entry, entry.default)

    def submit_message(self, message: Message) -> MessageResult:
        msg_uuid = str(uuid_mod.uuid4())
        now = datetime.now(UTC).isoformat()
        to_json = json.dumps(message.to)
        cc_json = json.dumps(message.cc) if message.cc else None
        bcc_json = json.dumps(message.bcc) if message.bcc else None

        conn = self._connect()
        try:
            blob_dir = resolve_blob_dir(self.db_path, self._setting(conn, "blobs.directory"))
            max_mb = int(self._setting(conn, "blobs.max_size_mb"))
            # Refuse before anything is written, as the server does
            for att in message.attachments:
                if len(att.data) > max_mb * 1024 * 1024:
                    raise ValueError(
                        f"Attachment too large: {att.filename} is {len(att.data)} bytes "
                        f"(max {max_mb} MB)"
                    )

            cursor = conn.cursor()

            def existing_disk_path(sha256: str) -> str | None:
                row = cursor.execute(
                    "SELECT disk_path FROM attachment WHERE sha256 = ? LIMIT 1", (sha256,)
                ).fetchone()
                return str(row[0]) if row else None

            # The message and its attachment rows commit together: the worker
            # must never find a queued message whose attachments are not there.
            cursor.execute("BEGIN IMMEDIATE;")
            try:
                cursor.execute(
                    "INSERT INTO message "
                    "(uuid, status, delivery_type, from_address, to_recipients, cc_recipients, "
                    "bcc_recipients, subject, body, body_type, retries_remaining, "
                    "source_app, created_at, updated_at) "
                    "VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, 5, ?, ?, ?)",
                    (
                        msg_uuid,
                        message.delivery_type,
                        message.from_address,
                        to_json,
                        cc_json,
                        bcc_json,
                        message.subject,
                        message.body,
                        message.body_type,
                        message.source_app,
                        now,
                        now,
                    ),
                )
                msg_id = conn.last_insert_rowid()
                for att in message.attachments:
                    sha256, disk_path = store_blob(blob_dir, att.data, existing_disk_path)
                    cursor.execute(
                        "INSERT INTO attachment "
                        "(message_id, filename, content_type, size_bytes, sha256, disk_path, "
                        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            msg_id,
                            att.filename,
                            att.content_type,
                            len(att.data),
                            sha256,
                            disk_path,
                            now,
                        ),
                    )
                cursor.execute("COMMIT;")
            except Exception:
                cursor.execute("ROLLBACK;")
                raise
        finally:
            conn.close()

        return MessageResult(uuid=msg_uuid, status="queued", created_at=now)

    def get_status(self, uuid: str) -> MessageResult | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT uuid, status, created_at, updated_at, sent_at, last_error "
                "FROM message WHERE uuid = ?",
                (uuid,),
            ).fetchone()
            if row is None:
                return None
            return _result_from_row(row)
        finally:
            conn.close()

    def list_messages(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MessageResult]:
        conn = self._connect()
        try:
            if status:
                rows = conn.execute(
                    "SELECT uuid, status, created_at, updated_at, sent_at, last_error "
                    "FROM message WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT uuid, status, created_at, updated_at, sent_at, last_error "
                    "FROM message ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [_result_from_row(row) for row in rows]
        finally:
            conn.close()

    def retry_message(self, uuid: str) -> MessageResult | None:
        conn = self._connect()
        try:
            now = datetime.now(UTC).isoformat()
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE;")
            try:
                row = cursor.execute(
                    "SELECT status FROM message WHERE uuid = ?", (uuid,)
                ).fetchone()
                if row is None:
                    cursor.execute("ROLLBACK;")
                    return None
                if row[0] not in ("failed", "dead"):
                    cursor.execute("ROLLBACK;")
                    return MessageResult(uuid=uuid, status=row[0])

                cursor.execute(
                    "UPDATE message SET status = 'queued', retries_remaining = 5, "
                    "next_retry_at = NULL, updated_at = ? WHERE uuid = ?",
                    (now, uuid),
                )
                cursor.execute("COMMIT;")
            except Exception:
                cursor.execute("ROLLBACK;")
                raise
            return MessageResult(uuid=uuid, status="queued", updated_at=now)
        finally:
            conn.close()

    def cancel_message(self, uuid: str) -> MessageResult | None:
        conn = self._connect()
        try:
            now = datetime.now(UTC).isoformat()
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE;")
            try:
                row = cursor.execute(
                    "SELECT status FROM message WHERE uuid = ?", (uuid,)
                ).fetchone()
                if row is None:
                    cursor.execute("ROLLBACK;")
                    return None
                if row[0] != "queued":
                    cursor.execute("ROLLBACK;")
                    return MessageResult(uuid=uuid, status=row[0])

                cursor.execute(
                    "UPDATE message SET status = 'cancelled', updated_at = ? WHERE uuid = ?",
                    (now, uuid),
                )
                cursor.execute("COMMIT;")
            except Exception:
                cursor.execute("ROLLBACK;")
                raise
            return MessageResult(uuid=uuid, status="cancelled", updated_at=now)
        finally:
            conn.close()
