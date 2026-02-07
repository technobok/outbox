# Outbox

Centralized mail queue service. Accepts messages via HTTP API or direct SQLite insertion, queues them, and delivers via SMTP with retries.

## Stack

- Python 3.14+, Flask, HTMX, PicoCSS
- SQLite/APSW database
- Authentication via [Gatekeeper](../gatekeeper) client library
- Background worker for SMTP delivery with exponential backoff

## Quick Start

```bash
make sync        # Install dependencies with uv
make init-db     # Create database
make rundev      # Start dev server on :5200
```

### Database location

By default the database is created at `instance/outbox.sqlite3` relative to the project root. Set the `OUTBOX_DB` environment variable to override:

```bash
export OUTBOX_DB=/data/outbox.sqlite3
```

The resolution order is:

1. `OUTBOX_DB` environment variable (if set)
2. Flask `DATABASE_PATH` config (when running inside the web server)
3. `instance/outbox.sqlite3` relative to the source tree (fallback)

All CLI commands (`outbox-admin`, `make config-*`, `make init-db`) and the web server use the same resolution logic — set `OUTBOX_DB` once and everything finds the database.

### Run with Docker

```bash
docker compose build
docker compose up -d        # Starts web + worker services
```

The container exposes port 5200 and persists data at `./instance/outbox.sqlite3` via a volume mount. Inside the container, `OUTBOX_ROOT` is set to `/app`.

## HTTP API

All endpoints require `X-API-Key` header. Generate keys via the admin UI or `make bootstrap-key`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/messages` | Submit message to queue |
| GET | `/api/v1/messages/<uuid>` | Get message status |
| GET | `/api/v1/messages` | List messages (paginated, filterable) |
| POST | `/api/v1/messages/<uuid>/retry` | Retry a failed/dead message |
| POST | `/api/v1/messages/<uuid>/cancel` | Cancel a queued message |

### Submit a message

```bash
curl -X POST http://localhost:5200/api/v1/messages \
  -H "X-API-Key: ob_..." \
  -H "Content-Type: application/json" \
  -d '{
    "from_address": "noreply@example.com",
    "to": ["user@example.com"],
    "subject": "Hello",
    "body": "Message content",
    "body_type": "plain"
  }'
```

Body types: `plain`, `html`, `markdown` (rendered to HTML with plain text fallback).

Attachments are supported via `attachments` array with base64-encoded content.

## Client Library

The client library is bundled as `outbox.client` and re-exported from the top-level package:

```python
from outbox import OutboxClient, Message

# Local mode (direct SQLite insertion, same machine)
client = OutboxClient(db_path="/path/to/outbox.sqlite3")

# HTTP mode (remote server)
client = OutboxClient(server_url="https://outbox.example.com", api_key="ob_...")

result = client.submit_message(Message(
    from_address="noreply@example.com",
    to=["user@example.com"],
    subject="Hello",
    body="World",
))
print(result.uuid, result.status)
```

## Message Flow

```
queued → sending → sent
                 → failed → (retry) → queued
                          → (exhausted) → dead
queued → cancelled
```

The worker process polls for queued messages, attempts SMTP delivery, and applies exponential backoff on failure. Dead and sent messages are purged after the configured retention period.

## Admin UI

The web interface (requires Gatekeeper auth) provides:

- **Dashboard** — queue statistics
- **Queue browser** — search, view, retry, cancel messages
- **API keys** — generate, toggle, delete
- **SQL** — direct database queries with schema reference

## Makefile reference

| Target | Description |
|---|---|
| `make sync` | Install/sync dependencies with uv |
| `make init-db` | Create a blank database |
| `make bootstrap-key` | Generate an API key (prints to console) |
| `make run` | Start production server (gunicorn, 0.0.0.0:5200) |
| `make rundev` | Start development server (Flask debug mode) |
| `make worker` | Start the queue worker process |
| `make config-list` | Show all configuration settings |
| `make config-set KEY=... VAL=...` | Set a configuration value |
| `make config-import FILE=...` | Import settings from an INI file |
| `make check` | Run ruff (format + lint) and ty (type check) |
| `make clean` | Remove bytecode and the database file |

## CLI commands

The `outbox-admin` CLI provides the same operations outside of Make:

```
outbox-admin init-db              # Initialize the database schema
outbox-admin generate-api-key     # Generate a new API key
outbox-admin config list          # Show settings
outbox-admin config set KEY VAL   # Set a setting
outbox-admin config import FILE   # Import from INI
```

## Configuration reference

All settings are stored in the SQLite database (`app_setting` table) and managed via `make config-set` or `outbox-admin config set`. Use `make config-list` to see current values.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `server.host` | string | `0.0.0.0` | Bind address for production server |
| `server.port` | int | `5200` | Port for production server |
| `server.dev_host` | string | `127.0.0.1` | Bind address for dev server |
| `server.dev_port` | int | `5200` | Port for dev server |
| `server.debug` | bool | `false` | Enable Flask debug mode |
| `mail.smtp_server` | string | | SMTP server hostname |
| `mail.smtp_port` | int | `587` | SMTP server port |
| `mail.smtp_use_tls` | bool | `true` | Use TLS for SMTP |
| `mail.smtp_username` | string | | SMTP authentication username |
| `mail.smtp_password` | string | | SMTP authentication password |
| `mail.mail_default_sender` | string | | Default sender address |
| `queue.poll_interval` | int | `5` | Queue poll interval in seconds |
| `queue.max_retries` | int | `5` | Maximum retry attempts per message |
| `queue.retry_base_seconds` | int | `120` | Base delay for exponential backoff (seconds) |
| `queue.retry_max_seconds` | int | `3600` | Maximum retry delay (seconds) |
| `queue.batch_size` | int | `10` | Messages to process per batch |
| `retention.days` | int | `30` | Days to keep sent/dead messages |
| `blobs.directory` | string | `instance/blobs` | Blob storage directory path |
| `blobs.max_size_mb` | int | `25` | Maximum blob size in MB |
| `auth.gatekeeper_db_path` | string | | Path to local Gatekeeper database |
| `auth.gatekeeper_url` | string | | Gatekeeper HTTP API base URL |
| `auth.gatekeeper_api_key` | string | | Gatekeeper API key |
| `proxy.x_forwarded_for` | int | `0` | Trust X-Forwarded-For (hop count) |
| `proxy.x_forwarded_proto` | int | `0` | Trust X-Forwarded-Proto (hop count) |
| `proxy.x_forwarded_host` | int | `0` | Trust X-Forwarded-Host (hop count) |
| `proxy.x_forwarded_prefix` | int | `0` | Trust X-Forwarded-Prefix (hop count) |

An `import` command is provided for initial bulk setup from an INI file — see `config.ini.example` for the format.
