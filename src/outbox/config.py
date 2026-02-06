"""Configuration registry and type system.

Every configurable setting is declared here with its key, type, default,
description, and whether it contains a secret.  The registry is the single
source of truth for what settings exist.
"""

from dataclasses import dataclass
from enum import Enum


class ConfigType(Enum):
    STRING = "string"
    INT = "int"
    BOOL = "bool"
    STRING_LIST = "string_list"


@dataclass(frozen=True, slots=True)
class ConfigEntry:
    key: str
    type: ConfigType
    default: str | int | bool | list[str]
    description: str
    secret: bool = False


# ---------------------------------------------------------------------------
# Registry -- every known setting
# ---------------------------------------------------------------------------

REGISTRY: list[ConfigEntry] = [
    # -- server --
    ConfigEntry("server.host", ConfigType.STRING, "0.0.0.0", "Bind address for production server"),
    ConfigEntry("server.port", ConfigType.INT, 5200, "Port for production server"),
    ConfigEntry("server.dev_host", ConfigType.STRING, "127.0.0.1", "Bind address for dev server"),
    ConfigEntry("server.dev_port", ConfigType.INT, 5200, "Port for dev server"),
    ConfigEntry("server.debug", ConfigType.BOOL, False, "Enable Flask debug mode"),
    # -- mail --
    ConfigEntry("mail.smtp_server", ConfigType.STRING, "", "SMTP server hostname"),
    ConfigEntry("mail.smtp_port", ConfigType.INT, 587, "SMTP server port"),
    ConfigEntry("mail.smtp_use_tls", ConfigType.BOOL, True, "Use TLS for SMTP"),
    ConfigEntry("mail.smtp_username", ConfigType.STRING, "", "SMTP authentication username"),
    ConfigEntry(
        "mail.smtp_password", ConfigType.STRING, "", "SMTP authentication password", secret=True
    ),
    ConfigEntry("mail.mail_default_sender", ConfigType.STRING, "", "Email sender address"),
    # -- queue --
    ConfigEntry("queue.poll_interval", ConfigType.INT, 5, "Queue poll interval in seconds"),
    ConfigEntry("queue.max_retries", ConfigType.INT, 5, "Maximum retry attempts per message"),
    ConfigEntry(
        "queue.retry_base_seconds", ConfigType.INT, 120, "Base delay for exponential backoff"
    ),
    ConfigEntry("queue.retry_max_seconds", ConfigType.INT, 3600, "Maximum retry delay in seconds"),
    ConfigEntry("queue.batch_size", ConfigType.INT, 10, "Messages to process per batch"),
    # -- retention --
    ConfigEntry("retention.days", ConfigType.INT, 30, "Days to keep sent/dead messages"),
    # -- blobs --
    ConfigEntry("blobs.directory", ConfigType.STRING, "instance/blobs", "Blob storage directory"),
    ConfigEntry("blobs.max_size_mb", ConfigType.INT, 25, "Maximum blob size in MB"),
    # -- auth --
    ConfigEntry("auth.gatekeeper_db_path", ConfigType.STRING, "", "Path to gatekeeper database"),
    ConfigEntry("auth.gatekeeper_url", ConfigType.STRING, "", "Gatekeeper HTTP API base URL"),
    ConfigEntry(
        "auth.gatekeeper_api_key", ConfigType.STRING, "", "Gatekeeper API key", secret=True
    ),
    # -- proxy --
    ConfigEntry("proxy.x_forwarded_for", ConfigType.INT, 0, "Trust X-Forwarded-For (hop count)"),
    ConfigEntry(
        "proxy.x_forwarded_proto", ConfigType.INT, 0, "Trust X-Forwarded-Proto (hop count)"
    ),
    ConfigEntry("proxy.x_forwarded_host", ConfigType.INT, 0, "Trust X-Forwarded-Host (hop count)"),
    ConfigEntry(
        "proxy.x_forwarded_prefix", ConfigType.INT, 0, "Trust X-Forwarded-Prefix (hop count)"
    ),
]

# Fast lookup by key
_REGISTRY_MAP: dict[str, ConfigEntry] = {e.key: e for e in REGISTRY}


def resolve_entry(key: str) -> ConfigEntry | None:
    """Look up a registry entry by key."""
    return _REGISTRY_MAP.get(key)


# ---------------------------------------------------------------------------
# Value parsing / serialization
# ---------------------------------------------------------------------------


def parse_value(entry: ConfigEntry, raw: str) -> str | int | bool | list[str]:
    """Parse a raw string value according to the entry's type."""
    match entry.type:
        case ConfigType.STRING:
            return raw
        case ConfigType.INT:
            return int(raw)
        case ConfigType.BOOL:
            return raw.lower() in ("true", "1", "yes", "on")
        case ConfigType.STRING_LIST:
            return [s.strip() for s in raw.split(",") if s.strip()]


def serialize_value(entry: ConfigEntry, value: str | int | bool | list[str]) -> str:
    """Serialize a typed value to a string for storage."""
    match entry.type:
        case ConfigType.BOOL:
            return "true" if value else "false"
        case ConfigType.STRING_LIST:
            if isinstance(value, list):
                return ", ".join(value)
            return str(value)
        case _:
            return str(value)


# ---------------------------------------------------------------------------
# Mapping from registry keys to Flask app.config keys
# ---------------------------------------------------------------------------

KEY_MAP: dict[str, str] = {
    "server.host": "HOST",
    "server.port": "PORT",
    "server.dev_host": "DEV_HOST",
    "server.dev_port": "DEV_PORT",
    "server.debug": "DEBUG",
    "mail.smtp_server": "SMTP_SERVER",
    "mail.smtp_port": "SMTP_PORT",
    "mail.smtp_use_tls": "SMTP_USE_TLS",
    "mail.smtp_username": "SMTP_USERNAME",
    "mail.smtp_password": "SMTP_PASSWORD",
    "mail.mail_default_sender": "MAIL_DEFAULT_SENDER",
    "queue.poll_interval": "QUEUE_POLL_INTERVAL",
    "queue.max_retries": "QUEUE_MAX_RETRIES",
    "queue.retry_base_seconds": "QUEUE_RETRY_BASE_SECONDS",
    "queue.retry_max_seconds": "QUEUE_RETRY_MAX_SECONDS",
    "queue.batch_size": "QUEUE_BATCH_SIZE",
    "retention.days": "RETENTION_DAYS",
    "blobs.directory": "BLOB_DIRECTORY",
    "blobs.max_size_mb": "BLOB_MAX_SIZE_MB",
    "auth.gatekeeper_db_path": "GATEKEEPER_DB_PATH",
    "auth.gatekeeper_url": "GATEKEEPER_URL",
    "auth.gatekeeper_api_key": "GATEKEEPER_API_KEY",
    "proxy.x_forwarded_for": "PROXY_X_FORWARDED_FOR",
    "proxy.x_forwarded_proto": "PROXY_X_FORWARDED_PROTO",
    "proxy.x_forwarded_host": "PROXY_X_FORWARDED_HOST",
    "proxy.x_forwarded_prefix": "PROXY_X_FORWARDED_PREFIX",
}


# ---------------------------------------------------------------------------
# INI section/key -> registry key mapping (for config import)
# ---------------------------------------------------------------------------

INI_MAP: dict[tuple[str, str], str | None] = {
    ("server", "HOST"): "server.host",
    ("server", "PORT"): "server.port",
    ("server", "DEV_HOST"): "server.dev_host",
    ("server", "DEV_PORT"): "server.dev_port",
    ("server", "DEBUG"): "server.debug",
    ("database", "PATH"): None,  # handled specially -- not a config setting
    ("mail", "SMTP_SERVER"): "mail.smtp_server",
    ("mail", "SMTP_PORT"): "mail.smtp_port",
    ("mail", "SMTP_USE_TLS"): "mail.smtp_use_tls",
    ("mail", "SMTP_USERNAME"): "mail.smtp_username",
    ("mail", "SMTP_PASSWORD"): "mail.smtp_password",
    ("mail", "MAIL_DEFAULT_SENDER"): "mail.mail_default_sender",
    ("queue", "POLL_INTERVAL"): "queue.poll_interval",
    ("queue", "MAX_RETRIES"): "queue.max_retries",
    ("queue", "RETRY_BASE_SECONDS"): "queue.retry_base_seconds",
    ("queue", "RETRY_MAX_SECONDS"): "queue.retry_max_seconds",
    ("queue", "BATCH_SIZE"): "queue.batch_size",
    ("retention", "DAYS"): "retention.days",
    ("blobs", "DIRECTORY"): "blobs.directory",
    ("blobs", "MAX_SIZE_MB"): "blobs.max_size_mb",
    ("auth", "GATEKEEPER_DB_PATH"): "auth.gatekeeper_db_path",
    ("auth", "GATEKEEPER_URL"): "auth.gatekeeper_url",
    ("auth", "GATEKEEPER_API_KEY"): "auth.gatekeeper_api_key",
    ("proxy", "X_FORWARDED_FOR"): "proxy.x_forwarded_for",
    ("proxy", "X_FORWARDED_PROTO"): "proxy.x_forwarded_proto",
    ("proxy", "X_FORWARDED_HOST"): "proxy.x_forwarded_host",
    ("proxy", "X_FORWARDED_PREFIX"): "proxy.x_forwarded_prefix",
}
