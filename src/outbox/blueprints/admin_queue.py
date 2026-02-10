"""Admin blueprint for queue browser (HTMX)."""

from flask import Blueprint, flash, g, redirect, render_template, request, send_file, url_for
from werkzeug.wrappers import Response

from outbox.blueprints.auth import login_required
from outbox.db import get_db
from outbox.models.attachment import Attachment
from outbox.models.message import Message

bp = Blueprint("admin_queue", __name__, url_prefix="/admin/queue")


def _audit_log(action: str, target: str | None = None, details: str | None = None) -> None:
    from datetime import UTC, datetime

    db = get_db()
    now = datetime.now(UTC).isoformat()
    actor = g.user.username if hasattr(g, "user") and g.user else None
    db.execute(
        "INSERT INTO audit_log (timestamp, actor, action, target, details) VALUES (?, ?, ?, ?, ?)",
        (now, actor, action, target, details),
    )


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


@bp.route("/")
@login_required
def index() -> str:
    """Queue browser: list messages with filters."""
    status = request.args.get("status")
    search = request.args.get("search", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    per_page = 50
    offset = (page - 1) * per_page

    messages = Message.list_messages(
        status=status if status else None,
        search=search if search else None,
        limit=per_page,
        offset=offset,
    )
    total = Message.count(status=status if status else None)
    total_pages = max((total + per_page - 1) // per_page, 1)
    stats = Message.stats()

    return render_template(
        "admin/queue.html",
        messages=messages,
        stats=stats,
        status=status or "",
        search=search,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@bp.route("/export")
@login_required
def export() -> Response:
    """Export current queue view as XLSX."""
    from outbox.services.export import write_xlsx

    status = request.args.get("status")
    search = request.args.get("search", "").strip()

    messages = Message.list_messages(
        status=status if status else None,
        search=search if search else None,
        limit=10000,
        offset=0,
    )
    headers = ["Status", "To", "Subject", "Source", "Created", "Sent"]
    data = [
        [
            m.status,
            m.to_recipients,
            m.subject,
            m.source_app or "",
            m.created_at,
            m.sent_at or "",
        ]
        for m in messages
    ]
    path = write_xlsx(headers, data, "queue.xlsx")
    _audit_log("queue_exported", details=f"{len(data)} messages exported")
    return send_file(path, as_attachment=True, download_name="queue.xlsx")


@bp.route("/<msg_uuid>")
@login_required
def detail(msg_uuid: str) -> str | Response:
    """View full message detail."""
    message = Message.get_by_uuid(msg_uuid)
    if message is None:
        flash("Message not found.", "error")
        return redirect(url_for("admin_queue.index"))

    attachments = Attachment.get_for_message(message.id)
    return render_template("admin/message_detail.html", message=message, attachments=attachments)


@bp.route("/<msg_uuid>/retry", methods=["POST"])
@login_required
def retry(msg_uuid: str) -> str | Response:
    """Retry a failed/dead message."""
    message = Message.get_by_uuid(msg_uuid)
    if message is None:
        flash("Message not found.", "error")
        return redirect(url_for("admin_queue.index"))

    if message.status not in ("failed", "dead"):
        flash(f"Cannot retry message with status '{message.status}'.", "error")
        return redirect(url_for("admin_queue.detail", msg_uuid=msg_uuid))

    from flask import current_app

    message.retries_remaining = current_app.config["QUEUE_MAX_RETRIES"]
    message.update_status("queued")
    _audit_log("message_retried", msg_uuid)
    flash("Message re-queued for delivery.", "success")

    if _is_htmx():
        attachments = Attachment.get_for_message(message.id)
        return render_template(
            "admin/message_detail.html", message=message, attachments=attachments
        )

    return redirect(url_for("admin_queue.detail", msg_uuid=msg_uuid))


@bp.route("/<msg_uuid>/cancel", methods=["POST"])
@login_required
def cancel(msg_uuid: str) -> str | Response:
    """Cancel a queued message."""
    message = Message.get_by_uuid(msg_uuid)
    if message is None:
        flash("Message not found.", "error")
        return redirect(url_for("admin_queue.index"))

    if message.status != "queued":
        flash(f"Cannot cancel message with status '{message.status}'.", "error")
        return redirect(url_for("admin_queue.detail", msg_uuid=msg_uuid))

    message.update_status("cancelled")
    _audit_log("message_cancelled", msg_uuid)
    flash("Message cancelled.", "success")

    if _is_htmx():
        attachments = Attachment.get_for_message(message.id)
        return render_template(
            "admin/message_detail.html", message=message, attachments=attachments
        )

    return redirect(url_for("admin_queue.detail", msg_uuid=msg_uuid))
