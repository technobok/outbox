"""Attachment storage service with SHA256 deduplication."""

from flask import current_app

from outbox.blobs import resolve_blob_dir, store_blob
from outbox.models.attachment import Attachment


def _existing_disk_path(sha256: str) -> str | None:
    existing = Attachment.find_by_sha256(sha256)
    return existing.disk_path if existing else None


def save_attachment(
    message_id: int,
    filename: str,
    content_type: str,
    data: bytes,
) -> Attachment:
    """Save attachment data to disk and create a database record.

    Uses SHA256 deduplication: if the same content already exists on disk,
    reuses the existing file path.
    """
    blob_dir = resolve_blob_dir(
        current_app.config["DATABASE_PATH"], current_app.config["BLOB_DIRECTORY"]
    )
    max_size = current_app.config["BLOB_MAX_SIZE_MB"] * 1024 * 1024

    if len(data) > max_size:
        raise ValueError(
            f"Attachment too large: {len(data)} bytes "
            f"(max {current_app.config['BLOB_MAX_SIZE_MB']} MB)"
        )

    sha256, disk_path = store_blob(blob_dir, data, _existing_disk_path)

    return Attachment.create(
        message_id=message_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        sha256=sha256,
        disk_path=disk_path,
    )
