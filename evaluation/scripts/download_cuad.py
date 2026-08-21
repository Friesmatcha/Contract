"""Download and safely extract the pinned CUAD v1 archive."""

from __future__ import annotations

import hashlib
import importlib
import json
import ntpath
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

yaml_module: Any = importlib.import_module("yaml")
yaml_error: type[BaseException] = getattr(yaml_module, "YAMLError", ValueError)
REPOSITORY_COMMIT = "67faa0e6023b04fcaae6cc09497ab00e5d63a2a2"
FIXED_DOWNLOAD_URL = (
    "https://github.com/The-Atticus-Project/cuad/raw/"
    f"{REPOSITORY_COMMIT}/data.zip"
)
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
CHUNK_SIZE = 1024 * 1024


class DownloadSafetyError(ValueError):
    """Raised when network or archive content is not safe to use."""


class _Response(Protocol):
    def read(self, size: int = -1) -> bytes: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *args: Any) -> None: ...


def download_cuad(
    manifest_path: Path,
    *,
    raw_dir: Path | None = None,
    opener: Any = urlopen,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    _validate_manifest(manifest)
    target_dir = raw_dir or manifest_path.parent.parent / "raw"
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / str(manifest["archive_filename"])
    extracted_path = target_dir / str(manifest["extracted_dir"])
    archive_fd, archive_name = tempfile.mkstemp(
        prefix=".cuad-download-", suffix=".tmp", dir=target_dir
    )
    os.close(archive_fd)
    temp_archive = Path(archive_name)
    temp_extract = Path(tempfile.mkdtemp(prefix=".cuad-extract-", dir=target_dir))
    owns_temp_extract = True
    try:
        actual_sha256, size_bytes = _download_to_temp(
            str(manifest["download_url"]), temp_archive, opener=opener
        )
        expected_sha256 = manifest.get("archive_sha256")
        if expected_sha256 and actual_sha256 != str(expected_sha256).lower():
            raise DownloadSafetyError("archive SHA-256 does not match manifest")
        if archive_path.exists():
            if _sha256_file(archive_path) != actual_sha256:
                raise DownloadSafetyError("existing archive has a different SHA-256")
            temp_archive.unlink()
        else:
            os.replace(temp_archive, archive_path)
        _safe_extract(archive_path, temp_extract)
        (temp_extract / ".complete").write_text(actual_sha256 + "\n", encoding="ascii")
        if extracted_path.exists():
            marker = extracted_path / ".complete"
            if not marker.is_file() or marker.read_text(encoding="ascii").strip() != actual_sha256:
                raise DownloadSafetyError("existing extracted dataset is not a verified match")
            shutil.rmtree(temp_extract)
        else:
            os.replace(temp_extract, extracted_path)
            owns_temp_extract = False
        result = {
            "dataset_id": manifest["dataset_id"],
            "dataset_version": manifest["dataset_version"],
            "repository_commit": manifest["repository_commit"],
            "archive_sha256": actual_sha256,
            "archive_size_bytes": size_bytes,
            "archive_filename": str(manifest["archive_filename"]),
            "extracted_dir": str(manifest["extracted_dir"]),
        }
        _write_json_atomic(target_dir / f"{manifest['dataset_id']}-download.json", result)
        return result
    except (OSError, HTTPError, URLError, zipfile.BadZipFile) as exc:
        raise DownloadSafetyError("CUAD download or extraction failed") from exc
    finally:
        if temp_archive.is_file():
            temp_archive.unlink()
        if owns_temp_extract and temp_extract.is_dir():
            shutil.rmtree(temp_extract)


def _download_to_temp(url: str, target: Path, *, opener: Any) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    request = Request(url, headers={"User-Agent": "contract-evaluation/1.0"})
    with opener(request, timeout=60) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise DownloadSafetyError("archive exceeds the download size limit")
            digest.update(chunk)
            handle.write(chunk)
    return digest.hexdigest(), size


def _safe_extract(archive_path: Path, destination: Path) -> None:
    seen: set[str] = set()
    total_size = 0
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            normalized = _safe_member_name(info.filename)
            key = normalized.casefold()
            if key in seen:
                raise DownloadSafetyError("archive contains duplicate paths")
            seen.add(key)
            mode = (info.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(mode):
                raise DownloadSafetyError("archive contains a symbolic link")
            if info.is_dir():
                (destination / normalized).mkdir(parents=True, exist_ok=True)
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                raise DownloadSafetyError("archive member exceeds the size limit")
            if info.compress_size == 0 and info.file_size > CHUNK_SIZE:
                raise DownloadSafetyError("archive member has an abnormal compression ratio")
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise DownloadSafetyError("archive member has an abnormal compression ratio")
            total_size += info.file_size
            if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise DownloadSafetyError("archive exceeds the uncompressed size limit")
            target = destination / normalized
            resolved_parent = target.parent.resolve()
            if os.path.commonpath((str(root), str(resolved_parent))) != str(root):
                raise DownloadSafetyError("archive member escapes extraction directory")
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with archive.open(info) as source, target.open("xb") as handle:
                while True:
                    chunk = source.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > info.file_size:
                        raise DownloadSafetyError("archive member size is inconsistent")
                    handle.write(chunk)
            if written != info.file_size:
                raise DownloadSafetyError("archive member is truncated")


def _safe_member_name(name: str) -> str:
    if not name or "\x00" in name or "\\" in name:
        raise DownloadSafetyError("archive contains an invalid path")
    if (
        PurePosixPath(name).is_absolute()
        or PureWindowsPath(name).is_absolute()
        or ntpath.isabs(name)
    ):
        raise DownloadSafetyError("archive contains an absolute path")
    parts = PurePosixPath(name).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise DownloadSafetyError("archive contains a path traversal")
    normalized = str(PurePosixPath(*parts))
    if not normalized:
        raise DownloadSafetyError("archive contains an empty path")
    return normalized


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("repository_commit") != REPOSITORY_COMMIT:
        raise DownloadSafetyError("manifest repository commit is not pinned")
    if manifest.get("download_url") != FIXED_DOWNLOAD_URL:
        raise DownloadSafetyError("manifest download URL is not the fixed HTTPS URL")
    if not str(manifest.get("download_url", "")).startswith("https://"):
        raise DownloadSafetyError("download URL must use HTTPS")
    digest = manifest.get("archive_sha256")
    if digest is not None and (not isinstance(digest, str) or len(digest) != 64):
        raise DownloadSafetyError("manifest archive_sha256 must be a SHA-256 hex string")


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = yaml_module.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, yaml_error) as exc:
        raise DownloadSafetyError("cannot read CUAD manifest") from exc
    if not isinstance(value, dict):
        raise DownloadSafetyError("CUAD manifest must be an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=".cuad-result-", suffix=".tmp", dir=path.parent
    )
    os.close(file_descriptor)
    temp = Path(temp_name)
    try:
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.is_file():
            temp.unlink()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    manifest = root / "evaluation" / "datasets" / "manifests" / "cuad-v1.yaml"
    try:
        result = download_cuad(manifest)
    except DownloadSafetyError as exc:
        print(f"download failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    print("record the reported archive_sha256 in the manifest before formal evaluation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
