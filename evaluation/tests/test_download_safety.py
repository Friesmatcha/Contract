from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from evaluation.scripts.download_cuad import (
    FIXED_DOWNLOAD_URL,
    REPOSITORY_COMMIT,
    DownloadSafetyError,
    _safe_extract,
    download_cuad,
)


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self, _size: int = -1) -> bytes:
        value, self.payload = self.payload, b""
        return value

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _zip(directory: Path, entries: list[tuple[str, bytes]]) -> Path:
    path = directory / "test.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    path.write_bytes(buffer.getvalue())
    return path


def test_rejects_traversal_absolute_and_duplicate_paths(tmp_path: Path) -> None:
    for name in ("../escape.txt", "/absolute.txt", "C:\\absolute.txt"):
        archive = tmp_path / name.replace("/", "_").replace("\\", "_").replace(":", "_")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zipped:
            zipped.writestr(name, b"x")
        archive.write_bytes(buffer.getvalue())
        with pytest.raises(DownloadSafetyError):
            _safe_extract(archive, tmp_path / (archive.stem + "-out"))

    archive = _zip(tmp_path, [("same.txt", b"a"), ("same.txt", b"b")])
    with pytest.raises(DownloadSafetyError):
        _safe_extract(archive, tmp_path / "duplicate-out")


def test_rejects_symlink_and_member_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        link = zipfile.ZipInfo("link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zipped.writestr(link, b"target")
    archive = tmp_path / "symlink.zip"
    archive.write_bytes(buffer.getvalue())
    with pytest.raises(DownloadSafetyError):
        _safe_extract(archive, tmp_path / "symlink-out")

    monkeypatch.setattr("evaluation.scripts.download_cuad.MAX_MEMBER_BYTES", 3)
    large = _zip(tmp_path, [("large.txt", b"1234")])
    with pytest.raises(DownloadSafetyError):
        _safe_extract(large, tmp_path / "large-out")


def test_failed_sha_does_not_leave_archive_or_temp_files(tmp_path: Path) -> None:
    manifest = tmp_path / "cuad-v1.yaml"
    manifest.write_text(
        "\n".join(
            [
                "dataset_id: cuad-v1",
                "dataset_version: v1",
                f"repository_commit: {REPOSITORY_COMMIT}",
                f"download_url: {FIXED_DOWNLOAD_URL}",
                "archive_filename: data.zip",
                "extracted_dir: extracted",
                "archive_sha256: " + "0" * 64,
            ]
        ),
        encoding="utf-8",
    )
    payload = b"not-the-expected-archive"

    def opener(request: object, *, timeout: float) -> _Response:
        return _Response(payload)

    with pytest.raises(DownloadSafetyError):
        download_cuad(manifest, raw_dir=tmp_path / "raw", opener=opener)
    raw = tmp_path / "raw"
    assert not (raw / "data.zip").exists()
    assert not list(raw.glob(".cuad-*"))


def test_success_records_archive_hash_and_extracts_atomically(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("test.json", b'{"data": []}')
    payload = buffer.getvalue()
    manifest = tmp_path / "cuad-v1.yaml"
    manifest.write_text(
        "\n".join(
            [
                "dataset_id: cuad-v1",
                "dataset_version: v1",
                f"repository_commit: {REPOSITORY_COMMIT}",
                f"download_url: {FIXED_DOWNLOAD_URL}",
                "archive_filename: data.zip",
                "extracted_dir: extracted",
                "archive_sha256: null",
            ]
        ),
        encoding="utf-8",
    )

    def opener(request: object, *, timeout: float) -> _Response:
        return _Response(payload)

    result = download_cuad(manifest, raw_dir=tmp_path / "raw", opener=opener)
    assert result["archive_sha256"] == hashlib.sha256(payload).hexdigest()
    recorded = json.loads(
        (tmp_path / "raw" / "cuad-v1-download.json").read_text()
    )
    assert recorded["archive_sha256"] == result["archive_sha256"]
    assert (tmp_path / "raw" / "extracted" / "test.json").exists()
    assert (
        (tmp_path / "raw" / "extracted" / ".complete").read_text().strip()
        == result["archive_sha256"]
    )
