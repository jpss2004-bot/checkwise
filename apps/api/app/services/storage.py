"""Pluggable upload storage.

Two backends ship today:

``LocalStorageService``
    Writes uploads under ``settings.LOCAL_STORAGE_PATH``. Used in dev and
    in CI tests.

``S3StorageService``
    Uploads to any S3-compatible bucket (AWS S3, Cloudflare R2, MinIO).
    The bytes still pass through a short-lived local temp file so PDF
    inspection (which reads from ``StoredFile.path``) keeps working
    without each caller having to know which backend is in use.

Pick a backend with ``STORAGE_BACKEND={local,s3}``. Routes should call
``get_storage_service()`` rather than instantiating a backend directly so
config drives the choice end-to-end.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import settings


class UploadTooLargeError(ValueError):
    """Raised by ``_stream_to_temp`` when the upload exceeds the cap.

    Subclasses ``ValueError`` so existing handlers that catch the bare
    ``ValueError`` keep working (back-compat). New handlers should
    catch this dedicated type so they can return HTTP 413 vs 400
    consistently — that's the M3 (2026-05-25) upload-413
    normalization contract.
    """


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    path: Path
    original_filename: str
    mime_type: str | None
    size_bytes: int
    sha256: str
    extension: str


class StorageService(Protocol):
    async def save_upload(self, upload: UploadFile) -> StoredFile: ...

    def save_bytes(
        self,
        *,
        storage_key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> None:  # pragma: no cover - protocol stub
        """Write raw bytes at a caller-chosen key.

        Used when the caller already holds the payload in memory (e.g.
        feedback screenshots which the API handler must read into bytes
        to magic-byte-validate). Overwrites if the key already exists.
        """
        ...

    def open_for_read(self, storage_key: str) -> Path:  # pragma: no cover - protocol stub
        """Return a local path the caller can read for the duration of the request."""
        ...

    def list_keys(self, prefix: str) -> list[str]:  # pragma: no cover - protocol stub
        """Return every storage key under ``prefix`` (recursive).

        Added for the metadata-export mirror (audit 2026-06-12): after a
        deploy wipes Render's ephemeral disk, the master-workbook rebuild
        needs to discover which per-slot workbooks exist in the durable
        backend before it can re-materialize them locally.
        """
        ...

    def presigned_download_url(
        self,
        storage_key: str,
        *,
        ttl_seconds: int | None = None,
        content_disposition: str | None = None,
    ) -> str | None:  # pragma: no cover - protocol stub
        """Return a time-limited download URL, or None when the backend serves files directly.

        Phase 5 / Slice 5A — ``content_disposition`` lets the caller
        override the response disposition the browser sees. S3 honors
        it via ``ResponseContentDisposition``; local backend returns
        None regardless (the API serves files directly with
        ``FileResponse``, which already controls disposition).
        """
        ...

    def delete(self, storage_key: str) -> None:  # pragma: no cover - protocol stub
        """Best-effort delete of ``storage_key``.

        Used by rollback paths (Stage 2.7-b multi-file submissions) to
        clean up bytes written before a downstream failure. Idempotent:
        deleting a missing key is a no-op, not an error.
        """
        ...


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", filename.strip()).strip("-")
    return cleaned or "documento"


async def _stream_to_temp(
    upload: UploadFile, *, max_bytes: int
) -> tuple[Path, str, int, str]:
    """Stream the upload into a temp file while hashing.

    Returns ``(temp_path, safe_filename, size_bytes, sha256_hex)``. The
    caller owns the temp file and is responsible for moving or deleting
    it. Enforces ``max_bytes`` so we never persist anything past the
    limit, even on the S3 path.
    """
    if not upload.filename:
        raise ValueError("El archivo no tiene nombre.")

    safe_name = _safe_filename(upload.filename)
    temp_dir = Path(tempfile.gettempdir()) / "checkwise-uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{hashlib.sha1(safe_name.encode()).hexdigest()}-{safe_name}"

    sha256 = hashlib.sha256()
    size = 0

    with temp_path.open("wb") as fh:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                temp_path.unlink(missing_ok=True)
                raise UploadTooLargeError(
                    f"El archivo excede el tamaño máximo permitido "
                    f"({max_bytes // (1024 * 1024)} MB)."
                )
            sha256.update(chunk)
            fh.write(chunk)

    return temp_path, safe_name, size, sha256.hexdigest()


def _storage_key_for(sha256_hex: str, safe_name: str) -> str:
    return f"documents/{sha256_hex[:2]}/{sha256_hex}/{safe_name}"


class LocalStorageService:
    def __init__(self, base_path: str | Path | None = None) -> None:
        self.base_path = Path(base_path or settings.LOCAL_STORAGE_PATH)

    async def save_upload(self, upload: UploadFile) -> StoredFile:
        temp_path, safe_name, size, digest = await _stream_to_temp(
            upload, max_bytes=settings.MAX_UPLOAD_SIZE_BYTES
        )
        storage_key = _storage_key_for(digest, safe_name)
        final_path = self.base_path / storage_key
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.replace(final_path)

        return StoredFile(
            storage_key=storage_key,
            path=final_path,
            original_filename=upload.filename or safe_name,
            mime_type=upload.content_type,
            size_bytes=size,
            sha256=digest,
            extension=Path(safe_name).suffix.lower(),
        )

    def save_bytes(
        self,
        *,
        storage_key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> None:
        # content_type is unused on the local backend — extensions in
        # storage_key carry the type. Kept in the signature so callers
        # don't have to branch on backend.
        _ = content_type
        final_path = self.base_path / storage_key
        final_path.parent.mkdir(parents=True, exist_ok=True)
        with final_path.open("wb") as fh:
            fh.write(data)

    def open_for_read(self, storage_key: str) -> Path:
        return self.base_path / storage_key

    def list_keys(self, prefix: str) -> list[str]:
        root = self.base_path / prefix
        if not root.is_dir():
            return []
        return sorted(
            str(item.relative_to(self.base_path).as_posix())
            for item in root.rglob("*")
            if item.is_file()
        )

    def presigned_download_url(
        self,
        storage_key: str,
        *,
        ttl_seconds: int | None = None,
        content_disposition: str | None = None,
    ) -> str | None:
        # Local backend serves files via the application directly, not
        # via signed URLs. ``content_disposition`` is unused on this
        # backend because the API sets disposition via FileResponse
        # headers in the caller.
        _ = ttl_seconds, content_disposition
        return None

    def delete(self, storage_key: str) -> None:
        """Delete the file at ``storage_key``. Idempotent.

        Missing files are treated as a no-op so rollback callers don't
        need to guard against double-cleanup. Unexpected OSErrors
        (permission denied, IO error) are swallowed — this method runs
        on the rollback path and must never raise, or the original
        error gets masked.
        """
        target = self.base_path / storage_key
        try:
            target.unlink(missing_ok=True)
        except OSError:
            # Best-effort cleanup; never propagate.
            pass


class S3StorageService:
    """S3-compatible backend.

    Uploads stream through a local temp file (so we hash + size-check the
    bytes once and PDF inspection still has a real file to read), then
    the temp file is uploaded to the bucket. The temp file is left in
    place for the duration of the request so callers can read it via
    ``StoredFile.path``; Render's ``/tmp`` is ephemeral so we don't need
    a sweeper for short-lived processes.
    """

    def __init__(
        self,
        *,
        bucket: str | None = None,
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        client=None,  # noqa: ANN001 - boto3 typing is loose; tests inject a moto client
    ) -> None:
        self.bucket = bucket or settings.STORAGE_BUCKET
        if client is not None:
            self._client = client
        else:
            self._client = _build_s3_client(
                endpoint_url=endpoint_url or settings.AWS_S3_ENDPOINT or None,
                region=region or settings.AWS_REGION or "auto",
                access_key_id=access_key_id or settings.AWS_ACCESS_KEY_ID or None,
                secret_access_key=secret_access_key or settings.AWS_SECRET_ACCESS_KEY or None,
            )

    async def save_upload(self, upload: UploadFile) -> StoredFile:
        temp_path, safe_name, size, digest = await _stream_to_temp(
            upload, max_bytes=settings.MAX_UPLOAD_SIZE_BYTES
        )
        storage_key = _storage_key_for(digest, safe_name)

        extra_args: dict[str, str] = {}
        if upload.content_type:
            extra_args["ContentType"] = upload.content_type
        # ENC-2 — assert encryption-at-rest in code rather than relying on
        # the bucket's default-encryption config. AWS S3 honors SSE-S3
        # (AES256); Cloudflare R2 encrypts at rest unconditionally and
        # accepts the header, so this is safe for both backends and makes
        # the at-rest guarantee auditable from the source. Configurable
        # (STORAGE_SSE_ALGORITHM="" disables) so a backend that ever
        # rejects the header can't break uploads.
        if settings.STORAGE_SSE_ALGORITHM:
            extra_args.setdefault("ServerSideEncryption", settings.STORAGE_SSE_ALGORITHM)

        def _do_upload() -> None:
            with temp_path.open("rb") as fh:
                self._client.upload_fileobj(
                    Fileobj=fh,
                    Bucket=self.bucket,
                    Key=storage_key,
                    ExtraArgs=extra_args or None,
                )

        # PERF-6 — boto3 is fully synchronous; calling ``upload_fileobj``
        # directly in this ``async def`` blocks the event loop for the
        # entire network PUT, stalling every other request on the worker
        # (worse with a single uvicorn worker). Offload to a thread.
        await run_in_threadpool(_do_upload)

        return StoredFile(
            storage_key=storage_key,
            path=temp_path,
            original_filename=upload.filename or safe_name,
            mime_type=upload.content_type,
            size_bytes=size,
            sha256=digest,
            extension=Path(safe_name).suffix.lower(),
        )

    def save_bytes(
        self,
        *,
        storage_key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> None:
        kwargs: dict[str, str | bytes] = {
            "Bucket": self.bucket,
            "Key": storage_key,
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        # ENC-2 — encryption-at-rest, asserted in code (see save_upload).
        if settings.STORAGE_SSE_ALGORITHM:
            kwargs["ServerSideEncryption"] = settings.STORAGE_SSE_ALGORITHM
        self._client.put_object(**kwargs)

    def open_for_read(self, storage_key: str) -> Path:
        """Materialize an object back to a local temp file and return its path.

        Used by retroactive operations (e.g. re-inspecting an older
        document). Single-shot — callers should not hold onto the path
        across requests.
        """
        temp_dir = Path(tempfile.gettempdir()) / "checkwise-downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(storage_key).suffix or ".bin"
        fd, name = tempfile.mkstemp(prefix="cw-", suffix=suffix, dir=temp_dir)
        # Close the fd; boto3 will reopen by path.
        import os

        os.close(fd)
        temp_path = Path(name)
        self._client.download_file(Bucket=self.bucket, Key=storage_key, Filename=str(temp_path))
        return temp_path

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def presigned_download_url(
        self,
        storage_key: str,
        *,
        ttl_seconds: int | None = None,
        content_disposition: str | None = None,
    ) -> str | None:
        ttl = ttl_seconds if ttl_seconds is not None else settings.S3_PRESIGNED_URL_TTL_SECONDS
        params: dict = {"Bucket": self.bucket, "Key": storage_key}
        # Slice 5A — when the caller wants the browser to save the
        # bytes as a file (not inline-render in a PDF viewer tab), we
        # pass ``ResponseContentDisposition`` into the signed URL so
        # S3 serves the response with the matching header. The
        # browser respects that even though the URL itself looks like
        # a plain object link.
        if content_disposition:
            params["ResponseContentDisposition"] = content_disposition
            # FILE GAP-6 — document downloads always set a disposition, so
            # this is the sensitive-bytes path. Instruct the browser/any
            # intermediary not to cache the object served via this signed
            # URL (it carries REPSE/tax/payroll evidence).
            params["ResponseCacheControl"] = "no-store, private"
        return self._client.generate_presigned_url(
            ClientMethod="get_object",
            Params=params,
            ExpiresIn=ttl,
        )

    def delete(self, storage_key: str) -> None:
        """Delete the object at ``storage_key``. Idempotent.

        S3 ``DeleteObject`` is already idempotent — it returns 204 for
        missing keys — so this is just a thin wrapper that swallows
        ClientError so rollback callers never see a storage exception
        mask the original failure.
        """
        try:
            self._client.delete_object(Bucket=self.bucket, Key=storage_key)
        except Exception:  # noqa: BLE001 — best-effort cleanup; never propagate
            pass


def _build_s3_client(
    *,
    endpoint_url: str | None,
    region: str,
    access_key_id: str | None,
    secret_access_key: str | None,
):  # noqa: ANN202 - boto3 client type is loose
    """Build a boto3 S3 client tuned for non-AWS providers (Cloudflare R2)."""
    import boto3
    from botocore.config import Config

    # R2 (and most non-AWS S3 providers) reject AWS's newer per-request
    # integrity checksums. ``when_required`` keeps the checksum logic
    # only for operations that mandate it (e.g. multipart finalize),
    # which is what R2 expects.
    # Bound every R2 call. Without explicit timeouts botocore defaults to ~60s
    # per attempt × 3 retries, so a hung/slow endpoint could pin a worker for
    # ~3 minutes on the metadata re-materialize and document-stream paths — and
    # the DB statement_timeout does NOT cover network I/O (perf audit P2-5).
    # ``read_timeout`` is the max gap between bytes, so a generous 60s keeps
    # legitimate large-object streams working while still failing a dead socket.
    config = Config(
        signature_version="s3v4",
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=10,
        read_timeout=60,
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=config,
    )


def get_storage_service() -> StorageService:
    """Return the storage backend selected by ``STORAGE_BACKEND``."""
    backend = (settings.STORAGE_BACKEND or "local").strip().lower()
    if backend == "s3":
        return S3StorageService()
    if backend == "local":
        return LocalStorageService()
    raise ValueError(
        f"STORAGE_BACKEND={settings.STORAGE_BACKEND!r} is not supported. "
        "Use 'local' or 's3'."
    )
