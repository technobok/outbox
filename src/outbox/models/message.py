"""Message queue model."""

import json
import uuid as uuid_mod
from dataclasses import dataclass
from datetime import UTC, datetime

from outbox.db import get_db, transaction

_MESSAGE_COLUMNS = (
    "id, uuid, status, delivery_type, from_address, to_recipients, cc_recipients, "
    "bcc_recipients, subject, body, body_type, retries_remaining, next_retry_at, "
    "last_error, source_app, source_api_key_id, created_at, updated_at, sent_at"
)


@dataclass
class Message:
    id: int
    uuid: str
    status: str
    delivery_type: str
    from_address: str
    to_recipients: str
    cc_recipients: str | None
    bcc_recipients: str | None
    subject: str
    body: str
    body_type: str
    retries_remaining: int
    next_retry_at: str | None
    last_error: str | None
    source_app: str | None
    source_api_key_id: int | None
    created_at: str
    updated_at: str
    sent_at: str | None

    @staticmethod
    def _from_row(row: tuple) -> Message:
        return Message(
            id=row[0],
            uuid=row[1],
            status=row[2],
            delivery_type=row[3],
            from_address=row[4],
            to_recipients=row[5],
            cc_recipients=row[6],
            bcc_recipients=row[7],
            subject=row[8],
            body=row[9],
            body_type=row[10],
            retries_remaining=row[11],
            next_retry_at=row[12],
            last_error=row[13],
            source_app=row[14],
            source_api_key_id=row[15],
            created_at=row[16],
            updated_at=row[17],
            sent_at=row[18],
        )

    def to_list(self) -> list[str]:
        """Parse to_recipients JSON into a list."""
        try:
            return json.loads(self.to_recipients)
        except json.JSONDecodeError, TypeError:
            return [self.to_recipients] if self.to_recipients else []

    def cc_list(self) -> list[str]:
        """Parse cc_recipients JSON into a list."""
        if not self.cc_recipients:
            return []
        try:
            return json.loads(self.cc_recipients)
        except json.JSONDecodeError, TypeError:
            return [self.cc_recipients]

    def bcc_list(self) -> list[str]:
        """Parse bcc_recipients JSON into a list."""
        if not self.bcc_recipients:
            return []
        try:
            return json.loads(self.bcc_recipients)
        except json.JSONDecodeError, TypeError:
            return [self.bcc_recipients]

    @staticmethod
    def create(
        from_address: str,
        to_recipients: list[str],
        subject: str = "",
        body: str = "",
        body_type: str = "plain",
        delivery_type: str = "email",
        cc_recipients: list[str] | None = None,
        bcc_recipients: list[str] | None = None,
        source_app: str | None = None,
        source_api_key_id: int | None = None,
        max_retries: int = 5,
    ) -> Message:
        """Create a new message in the queue."""
        msg_uuid = str(uuid_mod.uuid4())
        now = datetime.now(UTC).isoformat()
        to_json = json.dumps(to_recipients)
        cc_json = json.dumps(cc_recipients) if cc_recipients else None
        bcc_json = json.dumps(bcc_recipients) if bcc_recipients else None

        with transaction() as cursor:
            cursor.execute(
                "INSERT INTO message "
                "(uuid, status, delivery_type, from_address, to_recipients, cc_recipients, "
                "bcc_recipients, subject, body, body_type, retries_remaining, "
                "source_app, source_api_key_id, created_at, updated_at) "
                "VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    msg_uuid,
                    delivery_type,
                    from_address,
                    to_json,
                    cc_json,
                    bcc_json,
                    subject,
                    body,
                    body_type,
                    max_retries,
                    source_app,
                    source_api_key_id,
                    now,
                    now,
                ),
            )
            row = cursor.execute("SELECT last_insert_rowid()").fetchone()
            msg_id = int(row[0]) if row else 0

        return Message(
            id=msg_id,
            uuid=msg_uuid,
            status="queued",
            delivery_type=delivery_type,
            from_address=from_address,
            to_recipients=to_json,
            cc_recipients=cc_json,
            bcc_recipients=bcc_json,
            subject=subject,
            body=body,
            body_type=body_type,
            retries_remaining=max_retries,
            next_retry_at=None,
            last_error=None,
            source_app=source_app,
            source_api_key_id=source_api_key_id,
            created_at=now,
            updated_at=now,
            sent_at=None,
        )

    @staticmethod
    def get_by_uuid(msg_uuid: str) -> Message | None:
        """Get a message by UUID."""
        db = get_db()
        row = db.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM message WHERE uuid = ?", (msg_uuid,)
        ).fetchone()
        return Message._from_row(row) if row else None

    @staticmethod
    def get_by_id(msg_id: int) -> Message | None:
        """Get a message by ID."""
        db = get_db()
        row = db.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM message WHERE id = ?", (msg_id,)
        ).fetchone()
        return Message._from_row(row) if row else None

    def update_status(
        self,
        status: str,
        last_error: str | None = None,
        next_retry_at: str | None = None,
    ) -> None:
        """Update the message status."""
        now = datetime.now(UTC).isoformat()
        sent_at = now if status == "sent" else self.sent_at

        with transaction() as cursor:
            cursor.execute(
                "UPDATE message SET status = ?, last_error = ?, next_retry_at = ?, "
                "sent_at = ?, updated_at = ?, retries_remaining = ? WHERE id = ?",
                (
                    status,
                    last_error,
                    next_retry_at,
                    sent_at,
                    now,
                    self.retries_remaining,
                    self.id,
                ),
            )

        self.status = status
        self.last_error = last_error
        self.next_retry_at = next_retry_at
        self.updated_at = now
        if status == "sent":
            self.sent_at = now

    @staticmethod
    def list_messages(
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        """List messages with optional filters."""
        db = get_db()
        conditions = []
        params: list[str | int] = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if search:
            conditions.append(
                "(subject LIKE ? OR to_recipients LIKE ? OR from_address LIKE ? OR uuid LIKE ?)"
            )
            term = f"%{search}%"
            params.extend([term, term, term, term])

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.extend([limit, offset])

        rows = db.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM message{where} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
        return [Message._from_row(row) for row in rows]

    @staticmethod
    def count(status: str | None = None) -> int:
        """Count messages with optional status filter."""
        db = get_db()
        if status:
            row = db.execute("SELECT COUNT(*) FROM message WHERE status = ?", (status,)).fetchone()
        else:
            row = db.execute("SELECT COUNT(*) FROM message").fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def stats() -> dict[str, int]:
        """Get message count by status."""
        db = get_db()
        rows = db.execute("SELECT status, COUNT(*) FROM message GROUP BY status").fetchall()
        result: dict[str, int] = {str(row[0]): int(row[1] or 0) for row in rows}
        result["total"] = sum(result.values())
        return result

    @staticmethod
    def get_pending_batch(batch_size: int = 10) -> list[Message]:
        """Get a batch of messages ready for sending."""
        db = get_db()
        now = datetime.now(UTC).isoformat()
        rows = db.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM message "
            "WHERE status = 'queued' "
            "OR (status = 'failed' AND next_retry_at IS NOT NULL AND next_retry_at <= ?) "
            "ORDER BY created_at ASC LIMIT ?",
            (now, batch_size),
        ).fetchall()
        return [Message._from_row(row) for row in rows]

    @staticmethod
    def purge_old(retention_days: int) -> int:
        """Delete old sent/dead messages beyond retention period."""
        from datetime import timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()

        with transaction() as cursor:
            cursor.execute(
                "DELETE FROM message WHERE status IN ('sent', 'dead', 'cancelled') "
                "AND updated_at < ?",
                (cutoff,),
            )
            row = cursor.execute("SELECT changes()").fetchone()
            return int(row[0]) if row else 0
