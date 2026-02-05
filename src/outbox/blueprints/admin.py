"""Admin dashboard blueprint."""

from flask import Blueprint, current_app, flash, redirect, render_template, url_for

from outbox.blueprints.auth import login_required
from outbox.models.app_setting import AppSetting
from outbox.models.message import Message

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@login_required
def index():
    """Dashboard with queue statistics."""
    stats = Message.stats()
    secret_key = AppSetting.get_secret_key()
    return render_template("admin/index.html", stats=stats, secret_key=secret_key)


@bp.route("/rotate-secret-key", methods=["POST"])
@login_required
def rotate_secret_key():
    """Rotate the SECRET_KEY, invalidating all sessions."""
    new_key = AppSetting.rotate_secret_key()
    current_app.config["SECRET_KEY"] = new_key
    flash("Secret key rotated. All sessions have been invalidated.", "warning")
    return redirect(url_for("admin.index"))
