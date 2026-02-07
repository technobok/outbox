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

## Commands

| Command | Description |
|---------|-------------|
| `make sync` | Install dependencies with uv |
| `make init-db` | Initialize the database |
| `make run` | Production server via gunicorn (0.0.0.0:5200) |
| `make rundev` | Dev server with debug mode (127.0.0.1:5200) |
| `make worker` | Start the queue worker process |
| `make check` | Run ruff format/lint + ty typecheck |
| `make clean` | Remove temp files and database |

## Configuration

Copy `config.ini.example` to `config.ini` (or `instance/config.ini`) and edit.

Key sections: `[server]`, `[database]`, `[mail]` (SMTP), `[queue]` (poll/retry settings), `[retention]`, `[blobs]` (attachment storage), `[auth]` (Gatekeeper credentials).

## HTTP API

All endpoints require `X-API-Key` header. Generate keys via the admin UI or directly:

```python
from outbox import create_app
from outbox.models.api_key import ApiKey
app = create_app()
with app.app_context():
    key = ApiKey.generate(description="my service")
    print(key.key)  # ob_...
```

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

## Database Location

Default: `instance/outbox.sqlite3` (relative to project root).

Resolution order:
1. `OUTBOX_DB` environment variable (absolute path)
2. `DATABASE_PATH` in Flask config
3. `instance/outbox.sqlite3` under the detected project root (`OUTBOX_ROOT` env var, or auto-detected from source tree, or current working directory)

```bash
export OUTBOX_DB=/data/outbox.sqlite3   # override default location
```

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

The `outbox.client` sub-package can also be imported directly for finer-grained access:

```python
from outbox.client import OutboxClient
from outbox.client.models import MessageResult
```

## Message Flow

```
queued → sending → sent
                 → failed → (retry) → queued
                          → (exhausted) → dead
queued → cancelled
```

The worker process polls for queued messages, attempts SMTP delivery, and applies exponential backoff on failure. Dead and sent messages are purged after the configured retention period.

## Docker

```bash
docker compose up        # Starts web + worker services
```

## Admin UI

The web interface (requires Gatekeeper auth) provides:

- **Dashboard** — queue statistics
- **Queue browser** — search, view, retry, cancel messages
- **API keys** — generate, toggle, delete
- **SQL** — direct database queries with schema reference
