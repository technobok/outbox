"""Attachment storage service with SHA256 deduplication."""

import hashlib
from pathlib import Path

from flask import current_app

from outbox.models.attachment import Attachment


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
    blob_dir = Path(current_app.config["BLOB_DIRECTORY"])
    max_size = current_app.config["BLOB_MAX_SIZE_MB"] * 1024 * 1024

    if len(data) > max_size:
        raise ValueError(
            f"Attachment too large: {len(data)} bytes "
            f"(max {current_app.config['BLOB_MAX_SIZE_MB']} MB)"
        )

    sha256 = hashlib.sha256(data).hexdigest()

    # Check for existing file with same hash
    existing = Attachment.find_by_sha256(sha256)
    if existing and Path(existing.disk_path).exists():
        disk_path = existing.disk_path
    else:
        # Store in subdirectory based on first 2 chars of hash
        sub_dir = blob_dir / sha256[:2]
        sub_dir.mkdir(parents=True, exist_ok=True)
        disk_path = str(sub_dir / sha256)

        with open(disk_path, "wb") as f:
            f.write(data)

    return Attachment.create(
        message_id=message_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        sha256=sha256,
        disk_path=disk_path,
    )
