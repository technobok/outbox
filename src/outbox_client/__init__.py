"""Outbox Client Library - submit messages to the Outbox mail queue."""

from outbox_client.client import OutboxClient
from outbox_client.models import Attachment, Message, MessageStatus

__all__ = ["OutboxClient", "Message", "MessageStatus", "Attachment"]
