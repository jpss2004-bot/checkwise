from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    path: Path
    original_filename: str
    mime_type: str | None
    size_bytes: int
    sha256: str
    extension: str


class LocalStorageService:
    def __init__(self, base_path: str | Path | None = None) -> None:
        self.base_path = Path(base_path or settings.LOCAL_STORAGE_PATH)

    async def save_upload(self, upload: UploadFile) -> StoredFile:
        if not upload.filename:
            raise ValueError("El archivo no tiene nombre.")

        safe_name = self._safe_filename(upload.filename)
        extension = Path(safe_name).suffix.lower()
        temp_dir = self.base_path / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{hashlib.sha1(safe_name.encode()).hexdigest()}-{safe_name}"

        sha256 = hashlib.sha256()
        size = 0

        with temp_path.open("wb") as fh:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_SIZE_BYTES:
                    temp_path.unlink(missing_ok=True)
                    raise ValueError("El archivo excede el tamaño máximo permitido.")
                sha256.update(chunk)
                fh.write(chunk)

        digest = sha256.hexdigest()
        storage_key = f"documents/{digest[:2]}/{digest}/{safe_name}"
        final_path = self.base_path / storage_key
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.replace(final_path)

        return StoredFile(
            storage_key=storage_key,
            path=final_path,
            original_filename=upload.filename,
            mime_type=upload.content_type,
            size_bytes=size,
            sha256=digest,
            extension=extension,
        )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", filename.strip()).strip("-")
        return cleaned or "documento"
