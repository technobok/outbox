"""LocalBackend writes straight into the outbox database."""

from pathlib import Path

import pytest

from outbox.client import Attachment, Message
from outbox.client.backends.local import LocalBackend
from tests.conftest import query


def _message(**kwargs: object) -> Message:
    return Message(from_address="noreply@example.com", to=["a@example.com"], **kwargs)  # type: ignore[arg-type]


def test_attachments_are_stored(
    db_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a client runs in its own application's directory, not outbox's
    monkeypatch.chdir(tmp_path)
    result = LocalBackend(db_path).submit_message(
        _message(attachments=[Attachment("report.xlsx", "application/octet-stream", b"xlsx")])
    )

    rows = query(
        db_path,
        "SELECT a.filename, a.size_bytes, a.disk_path FROM attachment a "
        "JOIN message m ON m.id = a.message_id WHERE m.uuid = ?",
        (result.uuid,),
    )
    assert len(rows) == 1
    filename, size, disk_path = rows[0]
    assert (filename, size) == ("report.xlsx", 4)
    assert Path(disk_path).parent.parent == Path(db_path).parent / "blobs"
    assert Path(disk_path).read_bytes() == b"xlsx"


def test_oversize_attachment_inserts_nothing(db_path: str) -> None:
    query(db_path, "INSERT INTO app_setting (key, value) VALUES ('blobs.max_size_mb', '0')")
    with pytest.raises(ValueError, match="too large"):
        LocalBackend(db_path).submit_message(
            _message(attachments=[Attachment("big.bin", "application/octet-stream", b"x")])
        )
    assert query(db_path, "SELECT COUNT(*) FROM message") == [(0,)]
