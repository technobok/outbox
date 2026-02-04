"""Attachment metadata model."""

from dataclasses import dataclass
from datetime import UTC, datetime

from outbox.db import get_db, transaction

_ATTACHMENT_COLUMNS = (
    "id, message_id, filename, content_type, size_bytes, sha256, disk_path, created_at"
)


@dataclass
class Attachment:
    id: int
    message_id: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    disk_path: str
    created_at: str

    @staticmethod
    def _from_row(row: tuple) -> Attachment:
        return Attachment(
            id=row[0],
            message_id=row[1],
            filename=row[2],
            content_type=row[3],
            size_bytes=row[4],
            sha256=row[5],
            disk_path=row[6],
            created_at=row[7],
        )

    @staticmethod
    def create(
        message_id: int,
        filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        disk_path: str,
    ) -> Attachment:
        """Create a new attachment record."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            cursor.execute(
                "INSERT INTO attachment "
                "(message_id, filename, content_type, size_bytes, sha256, disk_path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (message_id, filename, content_type, size_bytes, sha256, disk_path, now),
            )
            row = cursor.execute("SELECT last_insert_rowid()").fetchone()
            att_id = int(row[0]) if row else 0

        return Attachment(
            id=att_id,
            message_id=message_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            disk_path=disk_path,
            created_at=now,
        )

    @staticmethod
    def get_for_message(message_id: int) -> list[Attachment]:
        """Get all attachments for a message."""
        db = get_db()
        rows = db.execute(
            f"SELECT {_ATTACHMENT_COLUMNS} FROM attachment WHERE message_id = ? ORDER BY id",
            (message_id,),
        ).fetchall()
        return [Attachment._from_row(row) for row in rows]

    @staticmethod
    def find_by_sha256(sha256: str) -> Attachment | None:
        """Find an existing attachment by SHA256 hash (for dedup)."""
        db = get_db()
        row = db.execute(
            f"SELECT {_ATTACHMENT_COLUMNS} FROM attachment WHERE sha256 = ? LIMIT 1",
            (sha256,),
        ).fetchone()
        return Attachment._from_row(row) if row else None
