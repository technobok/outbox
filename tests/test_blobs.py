"""Blob directory resolution is relative to the database, never to the cwd."""

from pathlib import Path

import pytest

from outbox.blobs import resolve_blob_dir, store_blob


@pytest.mark.parametrize("configured", ["blobs", "instance/blobs"])
def test_relative_resolves_against_db_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    db_path = str(tmp_path / "data" / "outbox.sqlite3")
    monkeypatch.chdir(tmp_path)
    assert resolve_blob_dir(db_path, configured) == tmp_path / "data" / "blobs"


def test_absolute_is_used_as_is(tmp_path: Path) -> None:
    blob_dir = tmp_path / "elsewhere"
    assert resolve_blob_dir(str(tmp_path / "outbox.sqlite3"), str(blob_dir)) == blob_dir


def test_store_blob_dedups(tmp_path: Path) -> None:
    sha, first = store_blob(tmp_path, b"hello", lambda _sha: None)
    assert Path(first).read_bytes() == b"hello"
    assert Path(first).is_absolute()
    assert store_blob(tmp_path, b"hello", lambda s: first if s == sha else None) == (sha, first)
