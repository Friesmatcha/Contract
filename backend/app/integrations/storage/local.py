import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import UUID


class LocalFileStore:
    """Local persistent-volume implementation of the FileStore boundary."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.quarantine_root = self.root / "quarantine"

    def create_quarantine_file(self) -> tuple[Path, BinaryIO]:
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(
            dir=self.quarantine_root,
            prefix="upload-",
            suffix=".tmp",
        )
        return Path(filename), os.fdopen(descriptor, "w+b")

    def promote(self, quarantine_path: Path, storage_key: str) -> None:
        target = self._path_for_key(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(quarantine_path, target)

    def open(self, storage_key: str) -> BinaryIO:
        return self._path_for_key(storage_key).open("rb")

    def exists(self, storage_key: str) -> bool:
        return self._path_for_key(storage_key).is_file()

    def delete(self, storage_key: str) -> None:
        self._path_for_key(storage_key).unlink(missing_ok=True)

    def remove_quarantine(self, quarantine_path: Path) -> None:
        quarantine_path.unlink(missing_ok=True)

    def _path_for_key(self, storage_key: str) -> Path:
        relative = PurePosixPath(storage_key)
        if (
            not storage_key
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or "\\" in storage_key
        ):
            raise ValueError("invalid storage key")
        candidate = (self.root / Path(*relative.parts)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("storage key escapes root") from exc
        return candidate


def file_storage_key(
    *, organization_id: UUID, contract_id: UUID, file_id: UUID
) -> str:
    return f"org/{organization_id}/contracts/{contract_id}/{file_id}"


__all__ = ["LocalFileStore", "file_storage_key"]
