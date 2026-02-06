"""Outbox - Centralized Mail Queue Service."""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import apsw
from flask import Flask

from outbox.config import KEY_MAP, REGISTRY, parse_value


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Application factory for Outbox."""
    # Resolve database path
    db_path = os.environ.get("OUTBOX_DB")
    if not db_path:
        if "OUTBOX_ROOT" in os.environ:
            project_root = Path(os.environ["OUTBOX_ROOT"])
        else:
            source_root = Path(__file__).parent.parent.parent
            if (source_root / "src" / "outbox" / "__init__.py").exists():
                project_root = source_root
            else:
                project_root = Path.cwd()
        db_path = str(project_root / "instance" / "outbox.sqlite3")
        instance_path = project_root / "instance"
    else:
        instance_path = Path(db_path).parent

    instance_path.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__, instance_path=str(instance_path), instance_relative_config=True)

    # Minimal defaults before DB config is loaded
    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE_PATH=db_path,
    )

    if test_config is not None:
        app.config.from_mapping(test_config)
    else:
        _load_config_from_db(app)

    from outbox.db import close_db

    app.teardown_appcontext(close_db)

    # Initialize gatekeeper_client
    gk_db_path = app.config.get("GATEKEEPER_DB_PATH", "")
    gk_url = app.config.get("GATEKEEPER_URL", "")
    gk_api_key = app.config.get("GATEKEEPER_API_KEY", "")

    if gk_db_path:
        from gatekeeper_client import GatekeeperClient

        gk = GatekeeperClient(db_path=gk_db_path)
        gk.init_app(app, cookie_name="gk_session")
        app.config["GATEKEEPER_CLIENT"] = gk
    elif gk_url and gk_api_key:
        from gatekeeper_client import GatekeeperClient

        gk = GatekeeperClient(server_url=gk_url, api_key=gk_api_key)
        gk.init_app(app, cookie_name="gk_session")
        app.config["GATEKEEPER_CLIENT"] = gk

    # Register blueprints
    from outbox.blueprints import admin, admin_keys, admin_queue, admin_sql, api, auth

    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(admin_keys.bp)
    app.register_blueprint(admin_queue.bp)
    app.register_blueprint(admin_sql.bp)

    # Jinja filters
    def _get_user_timezone() -> ZoneInfo:
        """Get user's timezone from request header or cookie."""
        from flask import request

        tz_name = request.headers.get("X-Timezone") or request.cookies.get("tz") or "UTC"
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo("UTC")

    @app.template_filter("localdate")
    def localdate_filter(iso_string: str | None) -> str:
        if not iso_string:
            return ""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            user_tz = _get_user_timezone()
            local_dt = dt.astimezone(user_tz)
            return local_dt.strftime("%b %d, %Y")
        except Exception:
            return iso_string[:10] if iso_string else ""

    @app.template_filter("localdatetime")
    def localdatetime_filter(iso_string: str | None) -> str:
        if not iso_string:
            return ""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            user_tz = _get_user_timezone()
            local_dt = dt.astimezone(user_tz)
            tz_abbr = local_dt.strftime("%Z")
            return local_dt.strftime(f"%b %d, %Y %H:%M {tz_abbr}")
        except Exception:
            return iso_string[:16].replace("T", " ") if iso_string else ""

    # Root route redirects to admin dashboard
    @app.route("/")
    def index():
        from flask import redirect, url_for

        return redirect(url_for("admin.index"))

    return app


def _load_config_from_db(app: Flask) -> None:
    """Load configuration from the database into Flask app.config."""
    db_path = app.config["DATABASE_PATH"]

    try:
        conn = apsw.Connection(db_path, flags=apsw.SQLITE_OPEN_READONLY)
    except apsw.CantOpenError:
        # Database doesn't exist yet (init-db hasn't been run)
        return

    try:
        rows = conn.execute("SELECT key, value FROM app_setting").fetchall()
    except apsw.SQLError:
        # Table doesn't exist yet
        conn.close()
        return

    db_values = {str(r[0]): str(r[1]) for r in rows}
    conn.close()

    # Load SECRET_KEY from database
    if "secret_key" in db_values:
        app.config["SECRET_KEY"] = db_values["secret_key"]

    # Apply registry entries
    for entry in REGISTRY:
        flask_key = KEY_MAP.get(entry.key)
        if not flask_key:
            continue

        raw = db_values.get(entry.key)
        if raw is not None:
            value = parse_value(entry, raw)
        else:
            value = entry.default

        app.config[flask_key] = value

    # Apply ProxyFix if any proxy values are non-zero
    x_for = app.config.get("PROXY_X_FORWARDED_FOR", 0)
    x_proto = app.config.get("PROXY_X_FORWARDED_PROTO", 0)
    x_host = app.config.get("PROXY_X_FORWARDED_HOST", 0)
    x_prefix = app.config.get("PROXY_X_FORWARDED_PREFIX", 0)
    if any((x_for, x_proto, x_host, x_prefix)):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=x_for, x_proto=x_proto, x_host=x_host, x_prefix=x_prefix
        )
