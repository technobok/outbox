"""Submitting a message to the queue: the one path for the API and the admin form."""

from dataclasses import dataclass

from flask import current_app

from outbox.blobs import resolve_blob_dir, store_blob
from outbox.db import transaction
from outbox.models.attachment import Attachment
from outbox.models.message import Message

BODY_TYPES = ("plain", "html", "markdown")


@dataclass
class NewAttachment:
    filename: str
    content_type: str
    data: bytes


def _refuse_line_breaks(field: str, addresses: list[str] | str | None) -> None:
    """An address is written into a mail header; a line break there would
    start a new header of the submitter's choosing."""
    if not addresses:
        return
    for address in [addresses] if isinstance(addresses, str) else addresses:
        if "\r" in str(address) or "\n" in str(address):
            raise ValueError(f"{field} addresses must not contain line breaks")


def _existing_disk_path(sha256: str) -> str | None:
    existing = Attachment.find_by_sha256(sha256)
    return existing.disk_path if existing else None


def submit_message(
    *,
    from_address: str,
    to: list[str],
    subject: str = "",
    body: str = "",
    body_type: str = "plain",
    delivery_type: str = "email",
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: list[str] | None = None,
    source_app: str | None = None,
    source_api_key_id: int | None = None,
    max_retries: int = 5,
    attachments: list[NewAttachment] | None = None,
) -> Message:
    """Validate a message and queue it with its attachments.

    Everything is checked before anything is written, and the message and its
    attachment rows commit together: the worker must never find a queued
    message whose attachments are still being saved. Raises ValueError, with a
    message fit to show the submitter, on bad input.
    """
    attachments = attachments or []

    if not from_address:
        raise ValueError("from_address is required")
    if not to or not isinstance(to, list):
        raise ValueError("to must be a non-empty list of email addresses")
    if body_type not in BODY_TYPES:
        raise ValueError("body_type must be plain, html, or markdown")
    _refuse_line_breaks("from", from_address)
    _refuse_line_breaks("to", to)
    _refuse_line_breaks("cc", cc)
    _refuse_line_breaks("bcc", bcc)
    # reply_to is new, so it can have the full rule without breaking anyone
    if reply_to is not None and not isinstance(reply_to, list):
        raise ValueError("reply_to must be a list of email addresses")
    for address in reply_to or []:
        if not isinstance(address, str) or "@" not in address:
            raise ValueError(f"reply_to address {address!r} is not an email address")
    _refuse_line_breaks("reply_to", reply_to)

    max_mb = current_app.config["BLOB_MAX_SIZE_MB"]
    for att in attachments:
        if len(att.data) > max_mb * 1024 * 1024:
            raise ValueError(
                f"Attachment too large: {att.filename} is {len(att.data)} bytes (max {max_mb} MB)"
            )

    blob_dir = resolve_blob_dir(
        current_app.config["DATABASE_PATH"], current_app.config["BLOB_DIRECTORY"]
    )
    with transaction() as cursor:
        message = Message.create(
            from_address=from_address,
            to_recipients=to,
            subject=subject,
            body=body,
            body_type=body_type,
            delivery_type=delivery_type,
            cc_recipients=cc or None,
            bcc_recipients=bcc or None,
            reply_to=reply_to or None,
            source_app=source_app,
            source_api_key_id=source_api_key_id,
            max_retries=max_retries,
            cursor=cursor,
        )
        for att in attachments:
            sha256, disk_path = store_blob(blob_dir, att.data, _existing_disk_path)
            Attachment.create(
                message_id=message.id,
                filename=att.filename,
                content_type=att.content_type,
                size_bytes=len(att.data),
                sha256=sha256,
                disk_path=disk_path,
                cursor=cursor,
            )
    return message
