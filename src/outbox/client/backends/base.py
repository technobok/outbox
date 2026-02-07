"""Abstract backend protocol for OutboxClient."""

from typing import Protocol

from outbox.client.models import Message, MessageResult


class OutboxBackend(Protocol):
    """Protocol that all backends must implement."""

    def submit_message(self, message: Message) -> MessageResult:
        """Submit a message to the queue."""
        ...

    def get_status(self, uuid: str) -> MessageResult | None:
        """Get the status of a message by UUID."""
        ...

    def list_messages(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MessageResult]:
        """List messages with optional filtering."""
        ...

    def retry_message(self, uuid: str) -> MessageResult | None:
        """Retry a failed/dead message."""
        ...

    def cancel_message(self, uuid: str) -> MessageResult | None:
        """Cancel a queued message."""
        ...
