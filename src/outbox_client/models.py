"""Standalone dataclasses for the Outbox client library."""

from dataclasses import dataclass, field
from enum import StrEnum


class MessageStatus(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"
    CANCELLED = "cancelled"


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class Message:
    from_address: str
    to: list[str]
    subject: str = ""
    body: str = ""
    body_type: str = "plain"
    delivery_type: str = "email"
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    source_app: str | None = None
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class MessageResult:
    uuid: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    sent_at: str | None = None
    last_error: str | None = None
