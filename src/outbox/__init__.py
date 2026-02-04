"""Outbox - Centralized Mail Queue Service."""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from flask import Flask

from outbox.config import load_config


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Application factory for Outbox."""
    if "OUTBOX_ROOT" in os.environ:
        project_root = Path(os.environ["OUTBOX_ROOT"])
    else:
        source_root = Path(__file__).parent.parent.parent
        if (source_root / "src" / "outbox" / "__init__.py").exists():
            project_root = source_root
        else:
            project_root = Path.cwd()

    instance_path = project_root / "instance"

    app = Flask(__name__, instance_path=str(instance_path), instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE_PATH=str(instance_path / "outbox.sqlite3"),
        HOST="0.0.0.0",
        PORT=5200,
        DEV_HOST="127.0.0.1",
        DEV_PORT=5200,
        DEBUG=False,
        # Mail defaults
        SMTP_SERVER="",
        SMTP_PORT=587,
        SMTP_USE_TLS=True,
        SMTP_USERNAME="",
        SMTP_PASSWORD="",
        MAIL_DEFAULT_SENDER="",
        # Queue defaults
        QUEUE_POLL_INTERVAL=5,
        QUEUE_MAX_RETRIES=5,
        QUEUE_RETRY_BASE_SECONDS=120,
        QUEUE_RETRY_MAX_SECONDS=3600,
        QUEUE_BATCH_SIZE=10,
        # Retention
        RETENTION_DAYS=30,
        # Blobs
        BLOB_DIRECTORY=str(instance_path / "blobs"),
        BLOB_MAX_SIZE_MB=25,
        # Gatekeeper auth
        GATEKEEPER_SECRET_KEY="",
        GATEKEEPER_DB_PATH="",
        GATEKEEPER_URL="",
        GATEKEEPER_API_KEY="",
    )

    if test_config is None:
        load_config(app, instance_path, project_root)
    else:
        app.config.from_mapping(test_config)

    instance_path.mkdir(parents=True, exist_ok=True)

    from outbox.db import close_db, init_db_command

    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

    # Initialize gatekeeper_client
    gk_secret = app.config["GATEKEEPER_SECRET_KEY"]
    if gk_secret:
        from gatekeeper_client import GatekeeperClient

        gk_db_path = app.config["GATEKEEPER_DB_PATH"]
        gk_url = app.config["GATEKEEPER_URL"]
        gk_api_key = app.config["GATEKEEPER_API_KEY"]

        if gk_db_path:
            gk = GatekeeperClient(secret_key=gk_secret, db_path=gk_db_path)
        elif gk_url and gk_api_key:
            gk = GatekeeperClient(secret_key=gk_secret, server_url=gk_url, api_key=gk_api_key)
        else:
            gk = None

        if gk:
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
