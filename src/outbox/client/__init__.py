"""Outbox Client Library - submit messages to the Outbox mail queue."""

from outbox.client.client import OutboxClient
from outbox.client.models import Attachment, Message, MessageStatus

__all__ = ["OutboxClient", "Message", "MessageStatus", "Attachment"]
