"""JSON API blueprint with API key authentication."""

import base64
import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Blueprint, g, jsonify, request
from werkzeug.wrappers import Response

from outbox.db import get_db
from outbox.models.api_key import ApiKey
from outbox.models.message import Message
from outbox.services.attachment_service import save_attachment

bp = Blueprint("api", __name__, url_prefix="/api/v1")


def api_key_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: require valid API key in X-API-Key header."""

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        raw_key = request.headers.get("X-API-Key", "")
        if not raw_key:
            return jsonify({"error": "Missing X-API-Key header"}), 401

        api_key = ApiKey.verify(raw_key)
        if api_key is None:
            return jsonify({"error": "Invalid or disabled API key"}), 401

        g.api_key = api_key
        return f(*args, **kwargs)

    return decorated


def _audit_log(action: str, target: str | None = None, details: str | None = None) -> None:
    from datetime import UTC, datetime

    db = get_db()
    now = datetime.now(UTC).isoformat()
    actor = f"api_key:{g.api_key.id}" if hasattr(g, "api_key") else None
    db.execute(
        "INSERT INTO audit_log (timestamp, actor, action, target, details) VALUES (?, ?, ?, ?, ?)",
        (now, actor, action, target, details),
    )


@bp.route("/messages", methods=["POST"])
@api_key_required
def submit_message() -> Response | tuple[Response, int]:
    """Submit a new message to the queue."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    from_address = data.get("from_address", "").strip()
    to = data.get("to")
    subject = data.get("subject", "")
    body = data.get("body", "")
    body_type = data.get("body_type", "plain")
    delivery_type = data.get("delivery_type", "email")
    cc = data.get("cc")
    bcc = data.get("bcc")
    source_app = data.get("source_app")
    attachments_data = data.get("attachments", [])

    if not from_address:
        return jsonify({"error": "from_address is required"}), 400
    if not to or not isinstance(to, list) or len(to) == 0:
        return jsonify({"error": "to must be a non-empty list of email addresses"}), 400
    if body_type not in ("plain", "html", "markdown"):
        return jsonify({"error": "body_type must be plain, html, or markdown"}), 400

    message = Message.create(
        from_address=from_address,
        to_recipients=to,
        subject=subject,
        body=body,
        body_type=body_type,
        delivery_type=delivery_type,
        cc_recipients=cc if cc else None,
        bcc_recipients=bcc if bcc else None,
        source_app=source_app,
        source_api_key_id=g.api_key.id,
    )

    # Handle attachments
    for att_data in attachments_data:
        filename = att_data.get("filename", "attachment")
        content_type = att_data.get("content_type", "application/octet-stream")
        content_b64 = att_data.get("content_base64", "")
        if content_b64:
            try:
                raw_data = base64.b64decode(content_b64)
            except Exception:
                return jsonify({"error": f"Invalid base64 in attachment '{filename}'"}), 400
            try:
                save_attachment(message.id, filename, content_type, raw_data)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

    _audit_log("message_submitted", message.uuid, json.dumps({"to": to, "subject": subject}))

    return jsonify(
        {
            "uuid": message.uuid,
            "status": message.status,
            "created_at": message.created_at,
        }
    ), 201


@bp.route("/messages/<msg_uuid>")
@api_key_required
def get_message(msg_uuid: str) -> Response | tuple[Response, int]:
    """Get a message by UUID."""
    message = Message.get_by_uuid(msg_uuid)
    if message is None:
        return jsonify({"error": "Message not found"}), 404

    return jsonify(_message_to_dict(message))


@bp.route("/messages")
@api_key_required
def list_messages() -> Response:
    """List messages with optional filtering."""
    status = request.args.get("status")
    search = request.args.get("search")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    messages = Message.list_messages(status=status, search=search, limit=limit, offset=offset)
    total = Message.count(status=status)

    return jsonify(
        {
            "messages": [_message_to_dict(m) for m in messages],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@bp.route("/messages/<msg_uuid>/retry", methods=["POST"])
@api_key_required
def retry_message(msg_uuid: str) -> Response | tuple[Response, int]:
    """Retry a failed/dead message."""
    message = Message.get_by_uuid(msg_uuid)
    if message is None:
        return jsonify({"error": "Message not found"}), 404

    if message.status not in ("failed", "dead"):
        return jsonify({"error": f"Cannot retry message with status '{message.status}'"}), 400

    from flask import current_app

    message.retries_remaining = current_app.config["QUEUE_MAX_RETRIES"]
    message.update_status("queued")
    _audit_log("message_retried", msg_uuid)

    return jsonify({"uuid": message.uuid, "status": message.status})


@bp.route("/messages/<msg_uuid>/cancel", methods=["POST"])
@api_key_required
def cancel_message(msg_uuid: str) -> Response | tuple[Response, int]:
    """Cancel a queued message."""
    message = Message.get_by_uuid(msg_uuid)
    if message is None:
        return jsonify({"error": "Message not found"}), 404

    if message.status != "queued":
        return jsonify({"error": f"Cannot cancel message with status '{message.status}'"}), 400

    message.update_status("cancelled")
    _audit_log("message_cancelled", msg_uuid)

    return jsonify({"uuid": message.uuid, "status": message.status})


def _message_to_dict(message: Message) -> dict[str, Any]:
    return {
        "uuid": message.uuid,
        "status": message.status,
        "delivery_type": message.delivery_type,
        "from_address": message.from_address,
        "to": message.to_list(),
        "cc": message.cc_list(),
        "bcc": message.bcc_list(),
        "subject": message.subject,
        "body_type": message.body_type,
        "retries_remaining": message.retries_remaining,
        "last_error": message.last_error,
        "source_app": message.source_app,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
        "sent_at": message.sent_at,
    }
