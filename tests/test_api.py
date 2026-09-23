"""The JSON submit API."""

import base64

from flask.testing import FlaskClient

from tests.conftest import query


def _post(client: FlaskClient, api_key: str, **fields: object):
    payload = {"from_address": "noreply@example.com", "to": ["a@example.com"], **fields}
    return client.post("/api/v1/messages", json=payload, headers={"X-API-Key": api_key})


def test_submit_with_attachment(client: FlaskClient, api_key: str, db_path: str) -> None:
    content = base64.b64encode(b"data").decode()
    resp = _post(client, api_key, attachments=[{"filename": "f.txt", "content_base64": content}])
    assert resp.status_code == 201
    rows = query(
        db_path,
        "SELECT a.filename FROM attachment a JOIN message m ON m.id = a.message_id "
        "WHERE m.uuid = ?",
        (resp.get_json()["uuid"],),
    )
    assert rows == [("f.txt",)]


def test_bad_base64_queues_nothing(client: FlaskClient, api_key: str, db_path: str) -> None:
    # b64decode skips stray characters but refuses bad padding
    resp = _post(client, api_key, attachments=[{"filename": "f", "content_base64": "abcde"}])
    assert resp.status_code == 400
    assert query(db_path, "SELECT COUNT(*) FROM message") == [(0,)]


def test_oversize_attachment_queues_nothing(
    client: FlaskClient, api_key: str, db_path: str
) -> None:
    content = base64.b64encode(b"x" * (1024 * 1024 + 1)).decode()
    resp = _post(client, api_key, attachments=[{"filename": "big", "content_base64": content}])
    assert resp.status_code == 400
    assert "too large" in resp.get_json()["error"]
    assert query(db_path, "SELECT COUNT(*) FROM message") == [(0,)]


def test_line_break_in_address_refused(client: FlaskClient, api_key: str, db_path: str) -> None:
    resp = _post(client, api_key, cc=["a@example.com\r\nBcc: victim@example.com"])
    assert resp.status_code == 400
    assert query(db_path, "SELECT COUNT(*) FROM message") == [(0,)]


def test_existing_rules_unchanged(client: FlaskClient, api_key: str) -> None:
    # an address without "@" was accepted before and still is
    assert _post(client, api_key, to=["postmaster"]).status_code == 201
    assert _post(client, api_key, to=[]).status_code == 400
    assert _post(client, api_key, from_address=" ").status_code == 400
    assert _post(client, api_key, body_type="rtf").status_code == 400
