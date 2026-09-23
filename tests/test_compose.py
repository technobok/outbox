"""The admin compose form queues a message with every field."""

import io
import json

from flask.testing import FlaskClient

from tests.conftest import query


def _form(**fields: object) -> dict[str, object]:
    return {
        "from_address": "noreply@example.com",
        "to": "a@example.com; b@example.com",
        "cc": "c@example.com",
        "bcc": "",
        "reply_to": "alice@example.com\nbob@example.com",
        "subject": "Test",
        "body": "# Hello",
        "body_type": "markdown",
        "delivery_type": "email",
        "source_app": "outbox-admin",
        "max_retries": "3",
        **fields,
    }


def test_get_renders(client: FlaskClient) -> None:
    resp = client.get("/admin/queue/new")
    assert resp.status_code == 200
    assert b'name="reply_to"' in resp.data


def test_send_queues_everything(client: FlaskClient, db_path: str) -> None:
    resp = client.post(
        "/admin/queue/new",
        data=_form(attachments=[(io.BytesIO(b"file"), "note.txt")]),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    uuid = resp.headers["Location"].rsplit("/", 1)[1]

    [row] = query(
        db_path,
        "SELECT id, to_recipients, cc_recipients, bcc_recipients, reply_to, subject, "
        "body_type, retries_remaining, source_app, source_api_key_id FROM message WHERE uuid = ?",
        (uuid,),
    )
    msg_id, to, cc, bcc, reply_to, subject, body_type, retries, source, key_id = row
    assert json.loads(to) == ["a@example.com", "b@example.com"]
    assert json.loads(cc) == ["c@example.com"]
    assert bcc is None
    assert json.loads(reply_to) == ["alice@example.com", "bob@example.com"]
    assert (subject, body_type, retries, source, key_id) == (
        "Test",
        "markdown",
        3,
        "outbox-admin",
        None,
    )
    assert query(db_path, "SELECT filename FROM attachment WHERE message_id = ?", (msg_id,)) == [
        ("note.txt",)
    ]
    assert query(db_path, "SELECT actor, action FROM audit_log") == [
        ("tester", "message_submitted")
    ]

    # the detail page shows it, and the next form remembers the sender
    assert b"alice@example.com, bob@example.com" in client.get(f"/admin/queue/{uuid}").data
    assert b'value="noreply@example.com"' in client.get("/admin/queue/new").data


def test_refused_submission_keeps_values(client: FlaskClient, db_path: str) -> None:
    resp = client.post("/admin/queue/new", data=_form(to="", subject="Keep me"))
    assert resp.status_code == 400
    assert b"Keep me" in resp.data
    assert b"non-empty list" in resp.data
    assert query(db_path, "SELECT COUNT(*) FROM message") == [(0,)]


def test_bad_max_retries(client: FlaskClient, db_path: str) -> None:
    assert client.post("/admin/queue/new", data=_form(max_retries="0")).status_code == 400
    assert client.post("/admin/queue/new", data=_form(max_retries="x")).status_code == 400
    assert query(db_path, "SELECT COUNT(*) FROM message") == [(0,)]


def test_queue_page_links_to_compose(client: FlaskClient) -> None:
    assert b"/admin/queue/new" in client.get("/admin/queue/").data
