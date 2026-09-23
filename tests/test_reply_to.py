"""Reply-To: stored, returned, sent as a header, and never a recipient."""

import json
from email import message_from_string

import pytest
from flask import Flask
from flask.testing import FlaskClient

from outbox.client import Message
from outbox.client.backends.local import LocalBackend
from tests.conftest import query


def test_api_round_trip(client: FlaskClient, api_key: str) -> None:
    headers = {"X-API-Key": api_key}
    resp = client.post(
        "/api/v1/messages",
        json={
            "from_address": "noreply@example.com",
            "to": ["a@example.com"],
            "reply_to": ["alice@example.com", "bob@example.com"],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    got = client.get(f"/api/v1/messages/{resp.get_json()['uuid']}", headers=headers).get_json()
    assert got["reply_to"] == ["alice@example.com", "bob@example.com"]


@pytest.mark.parametrize(
    "reply_to", ["alice@example.com", ["alice"], ["a@example.com\nBcc: x@example.com"], [3]]
)
def test_api_refuses_bad_reply_to(client: FlaskClient, api_key: str, reply_to: object) -> None:
    resp = client.post(
        "/api/v1/messages",
        json={"from_address": "n@example.com", "to": ["a@example.com"], "reply_to": reply_to},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 400


def test_api_without_reply_to(client: FlaskClient, api_key: str) -> None:
    headers = {"X-API-Key": api_key}
    resp = client.post(
        "/api/v1/messages",
        json={"from_address": "n@example.com", "to": ["a@example.com"]},
        headers=headers,
    )
    got = client.get(f"/api/v1/messages/{resp.get_json()['uuid']}", headers=headers).get_json()
    assert got["reply_to"] == []


def test_local_backend_migrates_and_stores(v1_db_path: str) -> None:
    result = LocalBackend(v1_db_path).submit_message(
        Message(from_address="n@example.com", to=["a@example.com"], reply_to=["alice@example.com"])
    )
    rows = query(v1_db_path, "SELECT reply_to FROM message WHERE uuid = ?", (result.uuid,))
    assert json.loads(rows[0][0]) == ["alice@example.com"]


def test_old_style_insert_still_works(db_path: str) -> None:
    # an old client library names no reply_to column
    query(
        db_path,
        "INSERT INTO message (uuid, from_address, to_recipients, created_at, updated_at) "
        "VALUES ('u1', 'n@example.com', '[\"a@example.com\"]', 'now', 'now')",
    )
    assert query(db_path, "SELECT reply_to FROM message WHERE uuid = 'u1'") == [(None,)]


class _FakeSMTP:
    sent: list[tuple[str, list[str], str]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def has_extn(self, name: str) -> bool:
        return False

    def sendmail(self, sender: str, recipients: list[str], body: str) -> None:
        _FakeSMTP.sent.append((sender, recipients, body))


def test_sent_as_header_not_recipient(app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    from outbox.models.message import Message as QueuedMessage
    from outbox.services import email_sender

    monkeypatch.setattr(email_sender.smtplib, "SMTP", _FakeSMTP)
    app.config.update(
        SMTP_SERVER="smtp.test",
        SMTP_PORT=25,
        SMTP_USE_TLS=False,
        SMTP_USERNAME="",
        SMTP_PASSWORD="",
        SMTP_TIMEOUT=5,
    )
    _FakeSMTP.sent.clear()
    with app.app_context():
        queued = QueuedMessage.create(
            from_address="noreply@example.com",
            to_recipients=["cust@example.com"],
            cc_recipients=["cc@example.com"],
            reply_to=["alice@example.com", "bob@example.com"],
            subject="s",
            body="b",
        )
        email_sender.send_message(QueuedMessage.get_by_id(queued.id))  # type: ignore[arg-type]

    [(sender, recipients, body)] = _FakeSMTP.sent
    assert sender == "noreply@example.com"
    assert recipients == ["cust@example.com", "cc@example.com"]
    assert message_from_string(body)["Reply-To"] == "alice@example.com, bob@example.com"
