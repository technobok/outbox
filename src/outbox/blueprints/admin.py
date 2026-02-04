"""Admin dashboard blueprint."""

from flask import Blueprint, render_template

from outbox.blueprints.auth import login_required
from outbox.models.message import Message

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@login_required
def index():
    """Dashboard with queue statistics."""
    stats = Message.stats()
    return render_template("admin/index.html", stats=stats)
