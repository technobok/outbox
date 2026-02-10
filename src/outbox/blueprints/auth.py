"""Authentication blueprint - login/logout/callback via gatekeeper_client."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.wrappers import Response

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _get_gk() -> Any:
    """Get the GatekeeperClient instance."""
    return current_app.config.get("GATEKEEPER_CLIENT")


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def login_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: require authentication via gatekeeper_client."""

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if g.get("user") is None:
            if _is_htmx():
                return "", 401
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)

    return decorated


def admin_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: require admin group membership."""

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if g.get("user") is None:
            if _is_htmx():
                return "", 401
            return redirect(url_for("auth.login", next=request.url))
        if not g.user.in_group("admin"):
            abort(403)
        return f(*args, **kwargs)

    return decorated


@bp.route("/login", methods=["GET", "POST"])
def login() -> str | Response:
    """Show login form or initiate magic link flow."""
    gk = _get_gk()

    if request.method == "GET":
        return render_template("auth/login.html", next_url=request.args.get("next", "/"))

    identifier = request.form.get("identifier", "").strip()
    next_url = request.form.get("next", "/")

    if not identifier:
        flash("Please enter your email or username.", "error")
        return render_template("auth/login.html", next_url=next_url)

    if not gk:
        flash("Authentication is not configured.", "error")
        return render_template("auth/login.html", next_url=next_url)

    callback_url = url_for("auth.callback", _external=True)
    sent = gk.send_magic_link(identifier, callback_url, redirect_url=next_url, app_name="Outbox")

    if not sent:
        logger.warning(f"Failed to send magic link for identifier: {identifier}")
        flash("Could not send login link. Check your email or username.", "error")
        return render_template("auth/login.html", next_url=next_url, identifier=identifier)

    flash("Login link sent! Check your email.", "success")
    return render_template("auth/login.html", next_url=next_url)


@bp.route("/callback")
def callback() -> Response:
    """Handle magic link callback from Gatekeeper."""
    gk = _get_gk()
    if not gk:
        abort(500)

    token = request.args.get("token")
    if not token:
        abort(400)

    result = gk.verify_magic_link(token)
    if result is None:
        flash("This login link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.login"))

    user, redirect_url = result

    if not user.in_group("admin"):
        flash("Access is restricted to administrators.", "error")
        return redirect(url_for("auth.login"))

    auth_token = gk.create_auth_token(user)
    response = make_response(redirect(redirect_url))
    response.set_cookie(
        "gk_session",
        auth_token,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
        max_age=86400,
    )
    return response


@bp.route("/logout", methods=["POST"])
def logout() -> Response:
    """Clear the auth cookie."""
    response = make_response(redirect(url_for("auth.login")))
    response.delete_cookie("gk_session")
    return response
