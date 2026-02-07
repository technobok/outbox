"""OutboxClient facade - unified API for both local and HTTP modes."""

from outbox.client.models import Message, MessageResult


class OutboxClient:
    """Main client for the Outbox mail queue service.

    Supports two modes:
    - Local mode: direct SQLite insertion (requires apsw)
    - HTTP mode: remote API calls (requires httpx)

    Usage:
        # Local mode (same machine, direct DB access)
        client = OutboxClient(db_path="/path/to/outbox.sqlite3")

        # HTTP mode (remote server)
        client = OutboxClient(server_url="https://outbox.example.com", api_key="ob_...")

        # Submit a message
        result = client.submit_message(Message(
            from_address="noreply@example.com",
            to=["user@example.com"],
            subject="Hello",
            body="World",
        ))

        # Check status
        status = client.get_status(result.uuid)
    """

    def __init__(
        self,
        db_path: str | None = None,
        server_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        if db_path:
            from outbox.client.backends.local import LocalBackend

            self.backend = LocalBackend(db_path)
            self.mode = "local"
        elif server_url and api_key:
            from outbox.client.backends.http import HttpBackend

            self.backend = HttpBackend(server_url, api_key)
            self.mode = "http"
        else:
            raise ValueError(
                "Provide either db_path (local mode) or server_url + api_key (HTTP mode)"
            )

    def submit_message(self, message: Message) -> MessageResult:
        """Submit a message to the queue."""
        return self.backend.submit_message(message)

    def get_status(self, uuid: str) -> MessageResult | None:
        """Get the status of a message by UUID."""
        return self.backend.get_status(uuid)

    def list_messages(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MessageResult]:
        """List messages with optional filtering."""
        return self.backend.list_messages(status=status, limit=limit, offset=offset)

    def retry_message(self, uuid: str) -> MessageResult | None:
        """Retry a failed/dead message."""
        return self.backend.retry_message(uuid)

    def cancel_message(self, uuid: str) -> MessageResult | None:
        """Cancel a queued message."""
        return self.backend.cancel_message(uuid)
