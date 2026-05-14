"""Storage backend tests.

Covers the LocalStorageService path against a tmp dir, the S3
implementation against a moto-mocked S3, and the factory's selection
logic. Also asserts the storage_key layout is identical across
backends so we can swap STORAGE_BACKEND without touching the schema.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import boto3
import pytest
from fastapi import UploadFile
from moto import mock_aws

from app.services.storage import (
    LocalStorageService,
    S3StorageService,
    get_storage_service,
)


def _fake_upload(name: str, body: bytes, content_type: str = "application/pdf") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(body), headers={"content-type": content_type})


def test_local_storage_stores_under_sha_keyed_path(tmp_path: Path) -> None:
    body = b"%PDF-1.4 hola mundo"
    upload = _fake_upload("acta-constitutiva.pdf", body)
    svc = LocalStorageService(base_path=tmp_path)

    stored = asyncio.run(svc.save_upload(upload))

    # storage_key shape: documents/<2-char-prefix>/<full-sha>/<safe-name>
    parts = stored.storage_key.split("/")
    assert parts[0] == "documents"
    assert len(parts[1]) == 2
    assert len(parts[2]) == 64
    assert parts[3] == "acta-constitutiva.pdf"
    assert stored.size_bytes == len(body)
    assert stored.extension == ".pdf"
    assert (tmp_path / stored.storage_key).exists()
    assert (tmp_path / stored.storage_key).read_bytes() == body


def test_local_storage_rejects_oversize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import storage as storage_mod

    monkeypatch.setattr(storage_mod.settings, "MAX_UPLOAD_SIZE_BYTES", 8)
    svc = LocalStorageService(base_path=tmp_path)
    upload = _fake_upload("big.pdf", b"%PDF-1.4 way too many bytes")

    with pytest.raises(ValueError, match="excede"):
        asyncio.run(svc.save_upload(upload))


def test_local_storage_sanitizes_filenames(tmp_path: Path) -> None:
    """Spaces and shell metacharacters are stripped from filenames; the
    sha-keyed prefix is what guarantees the final path stays inside
    base_path even if the basename starts with a dot."""
    upload = _fake_upload("../weird name $$ .pdf", b"%PDF-1.4 x")
    svc = LocalStorageService(base_path=tmp_path)
    stored = asyncio.run(svc.save_upload(upload))

    tail = stored.storage_key.split("/")[-1]
    assert " " not in tail
    assert "$" not in tail
    assert tail.endswith(".pdf")
    # Traversal safety: the resolved file must live under base_path.
    resolved = (tmp_path / stored.storage_key).resolve()
    assert str(resolved).startswith(str(tmp_path.resolve()))


@mock_aws
def test_s3_storage_uploads_to_bucket_and_matches_local_key_shape() -> None:
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="checkwise-test")
    svc = S3StorageService(bucket="checkwise-test", client=client)

    body = b"%PDF-1.4 hola s3"
    upload = _fake_upload("rfc-constancia.pdf", body)
    stored = asyncio.run(svc.save_upload(upload))

    # Same key layout as LocalStorageService — that's the swap guarantee.
    parts = stored.storage_key.split("/")
    assert parts[0] == "documents"
    assert len(parts[1]) == 2
    assert len(parts[2]) == 64
    assert parts[3] == "rfc-constancia.pdf"

    obj = client.get_object(Bucket="checkwise-test", Key=stored.storage_key)
    assert obj["Body"].read() == body
    # ContentType is propagated when the upload carries one.
    assert obj["ContentType"] == "application/pdf"


@mock_aws
def test_s3_storage_path_is_a_real_local_file_for_inspection() -> None:
    """Routes call inspect_pdf(stored_file.path) immediately after save_upload.
    The S3 backend must still hand back a real local path that exists,
    so that downstream PDF inspection works without a separate download."""
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="checkwise-test")
    svc = S3StorageService(bucket="checkwise-test", client=client)

    body = b"%PDF-1.4 contenido"
    stored = asyncio.run(svc.save_upload(_fake_upload("x.pdf", body)))

    assert stored.path.exists()
    assert stored.path.read_bytes() == body


@mock_aws
def test_s3_storage_presigned_url_is_signed() -> None:
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="checkwise-test")
    svc = S3StorageService(bucket="checkwise-test", client=client)
    stored = asyncio.run(svc.save_upload(_fake_upload("a.pdf", b"%PDF-1.4 a")))

    url = svc.presigned_download_url(stored.storage_key, ttl_seconds=60)

    assert url is not None
    assert "checkwise-test" in url
    # Accept either SigV2 (Signature=...) or SigV4 (X-Amz-Signature=...).
    # moto returns SigV2 for the default AWS endpoint, real R2/S3 return SigV4.
    assert "Signature=" in url
    # ttl is reflected — either as X-Amz-Expires=<seconds> or as Expires=<unix-ts>.
    assert "Expires" in url


@mock_aws
def test_s3_storage_open_for_read_downloads_back() -> None:
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="checkwise-test")
    svc = S3StorageService(bucket="checkwise-test", client=client)
    body = b"%PDF-1.4 round-trip"
    stored = asyncio.run(svc.save_upload(_fake_upload("rt.pdf", body)))

    local = svc.open_for_read(stored.storage_key)

    assert local.exists()
    assert local.read_bytes() == body


def test_factory_returns_local_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import storage as storage_mod

    monkeypatch.setattr(storage_mod.settings, "STORAGE_BACKEND", "local")
    svc = get_storage_service()
    assert isinstance(svc, LocalStorageService)


def test_factory_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import storage as storage_mod

    monkeypatch.setattr(storage_mod.settings, "STORAGE_BACKEND", "azure-blob")
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        get_storage_service()
