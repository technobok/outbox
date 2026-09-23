"""Attachment blob storage on disk, shared by the server and the LocalBackend client.

No Flask here: the client library's LocalBackend runs inside other applications
and writes blobs into the same directory the outbox worker reads them from.
"""

import hashlib
from collections.abc import Callable
from pathlib import Path


def resolve_blob_dir(db_path: str, configured: str) -> Path:
    """The absolute blob directory for the database at db_path.

    A relative blobs.directory is relative to the database's directory, never to
    the process's cwd: the web server, the worker and a LocalBackend client
    inside another application all run from different directories (and in
    Docker, different containers), but they share the database's directory.

    The old default was "instance/blobs", meant relative to the project root
    whose instance/ holds the database, so a leading "instance" component is
    dropped - that value still names <db dir>/blobs.
    """
    path = Path(configured)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "instance":
        path = Path(*path.parts[1:])
    return Path(db_path).resolve().parent / path


def store_blob(
    blob_dir: Path,
    data: bytes,
    find_existing: Callable[[str], str | None],
) -> tuple[str, str]:
    """Store data under blob_dir, returning (sha256, disk_path).

    find_existing maps a sha256 to the disk_path of an attachment already
    holding that content, if any; when that file is still there it is reused
    instead of writing a second copy.
    """
    sha256 = hashlib.sha256(data).hexdigest()

    existing = find_existing(sha256)
    if existing and Path(existing).exists():
        return sha256, existing

    # Store in subdirectory based on first 2 chars of hash
    sub_dir = blob_dir / sha256[:2]
    sub_dir.mkdir(parents=True, exist_ok=True)
    disk_path = sub_dir / sha256
    disk_path.write_bytes(data)
    return sha256, str(disk_path)
