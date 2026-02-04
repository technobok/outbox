"""Configuration loading helpers."""

import configparser
from pathlib import Path


def load_config(app, instance_path: Path, project_root: Path) -> None:
    """Load configuration from config.ini into Flask app config."""
    config_path = instance_path / "config.ini"
    if not config_path.exists():
        config_path = project_root / "config.ini"

    if not config_path.exists():
        return

    config = configparser.ConfigParser()
    config.read(config_path)

    if config.has_section("server"):
        if config.has_option("server", "SECRET_KEY"):
            app.config["SECRET_KEY"] = config.get("server", "SECRET_KEY")
        if config.has_option("server", "HOST"):
            app.config["HOST"] = config.get("server", "HOST")
        if config.has_option("server", "PORT"):
            app.config["PORT"] = config.getint("server", "PORT")
        if config.has_option("server", "DEV_HOST"):
            app.config["DEV_HOST"] = config.get("server", "DEV_HOST")
        if config.has_option("server", "DEV_PORT"):
            app.config["DEV_PORT"] = config.getint("server", "DEV_PORT")
        if config.has_option("server", "DEBUG"):
            app.config["DEBUG"] = config.getboolean("server", "DEBUG")

    if config.has_section("database"):
        if config.has_option("database", "PATH"):
            db_path = config.get("database", "PATH")
            if not Path(db_path).is_absolute():
                db_path = str(project_root / db_path)
            app.config["DATABASE_PATH"] = db_path

    if config.has_section("mail"):
        app.config["SMTP_SERVER"] = config.get("mail", "SMTP_SERVER", fallback="")
        app.config["SMTP_PORT"] = config.getint("mail", "SMTP_PORT", fallback=587)
        app.config["SMTP_USE_TLS"] = config.getboolean("mail", "SMTP_USE_TLS", fallback=True)
        app.config["SMTP_USERNAME"] = config.get("mail", "SMTP_USERNAME", fallback="")
        app.config["SMTP_PASSWORD"] = config.get("mail", "SMTP_PASSWORD", fallback="")
        app.config["MAIL_DEFAULT_SENDER"] = config.get("mail", "MAIL_DEFAULT_SENDER", fallback="")

    if config.has_section("queue"):
        app.config["QUEUE_POLL_INTERVAL"] = config.getint("queue", "POLL_INTERVAL", fallback=5)
        app.config["QUEUE_MAX_RETRIES"] = config.getint("queue", "MAX_RETRIES", fallback=5)
        app.config["QUEUE_RETRY_BASE_SECONDS"] = config.getint(
            "queue", "RETRY_BASE_SECONDS", fallback=120
        )
        app.config["QUEUE_RETRY_MAX_SECONDS"] = config.getint(
            "queue", "RETRY_MAX_SECONDS", fallback=3600
        )
        app.config["QUEUE_BATCH_SIZE"] = config.getint("queue", "BATCH_SIZE", fallback=10)

    if config.has_section("retention"):
        app.config["RETENTION_DAYS"] = config.getint("retention", "DAYS", fallback=30)

    if config.has_section("blobs"):
        blob_dir = config.get("blobs", "DIRECTORY", fallback="instance/blobs")
        if not Path(blob_dir).is_absolute():
            blob_dir = str(project_root / blob_dir)
        app.config["BLOB_DIRECTORY"] = blob_dir
        app.config["BLOB_MAX_SIZE_MB"] = config.getint("blobs", "MAX_SIZE_MB", fallback=25)

    if config.has_section("auth"):
        app.config["GATEKEEPER_SECRET_KEY"] = config.get(
            "auth", "GATEKEEPER_SECRET_KEY", fallback=""
        )
        app.config["GATEKEEPER_DB_PATH"] = config.get("auth", "GATEKEEPER_DB_PATH", fallback="")
        app.config["GATEKEEPER_URL"] = config.get("auth", "GATEKEEPER_URL", fallback="")
        app.config["GATEKEEPER_API_KEY"] = config.get("auth", "GATEKEEPER_API_KEY", fallback="")

    if config.has_section("proxy"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        x_for = config.getint("proxy", "X_FORWARDED_FOR", fallback=1)
        x_proto = config.getint("proxy", "X_FORWARDED_PROTO", fallback=1)
        x_host = config.getint("proxy", "X_FORWARDED_HOST", fallback=1)
        x_prefix = config.getint("proxy", "X_FORWARDED_PREFIX", fallback=0)
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=x_for, x_proto=x_proto, x_host=x_host, x_prefix=x_prefix
        )
