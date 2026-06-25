"""Metadata-export durability (audit 2026-06-12).

Covers the three legs of the ephemeral-disk fix:

1. Settings anchoring — relative LOCAL_STORAGE_PATH / METADATA_EXPORT_PATH
   resolve against the apps/api root, not the process CWD (the old
   behavior scattered files across three storage directories).
2. ``StorageService.list_keys`` — recursive key listing on both backends,
   added so the master rebuild can discover mirrored workbooks.
3. The ``metadata_store`` mirror — persist / re-materialize / sync, plus
   the export-root containment guard and the local-backend no-op.
"""

from __future__ import annotations

from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from app.core.config import Settings
from app.services import metadata_store
from app.services.storage import LocalStorageService, S3StorageService

# ---------------------------------------------------------------------------
# 1. Relative-path anchoring
# ---------------------------------------------------------------------------


def test_relative_storage_paths_anchor_to_api_root() -> None:
    s = Settings(LOCAL_STORAGE_PATH="./storage", METADATA_EXPORT_PATH="./metadata_exports")
    api_root = Path(__file__).resolve().parents[1]
    assert Path(s.LOCAL_STORAGE_PATH) == api_root / "storage"
    assert Path(s.METADATA_EXPORT_PATH) == api_root / "metadata_exports"


def test_absolute_storage_paths_pass_through(tmp_path: Path) -> None:
    s = Settings(
        LOCAL_STORAGE_PATH=str(tmp_path / "blobs"),
        METADATA_EXPORT_PATH=str(tmp_path / "exports"),
    )
    assert Path(s.LOCAL_STORAGE_PATH) == tmp_path / "blobs"
    assert Path(s.METADATA_EXPORT_PATH) == tmp_path / "exports"


# ---------------------------------------------------------------------------
# 2. list_keys on both backends
# ---------------------------------------------------------------------------


def test_local_list_keys_recurses_and_is_rooted(tmp_path: Path) -> None:
    svc = LocalStorageService(base_path=tmp_path)
    svc.save_bytes(storage_key="metadata_exports/acme/v1/latest_metadata.xlsx", data=b"a")
    svc.save_bytes(storage_key="metadata_exports/acme/v2/latest_metadata.xlsx", data=b"b")
    svc.save_bytes(storage_key="metadata_exports/otra/latest_metadata.xlsx", data=b"c")
    svc.save_bytes(storage_key="documents/aa/whatever.pdf", data=b"d")

    keys = svc.list_keys("metadata_exports/acme")

    assert keys == [
        "metadata_exports/acme/v1/latest_metadata.xlsx",
        "metadata_exports/acme/v2/latest_metadata.xlsx",
    ]
    assert svc.list_keys("metadata_exports/no-such-client") == []


@mock_aws
def test_s3_list_keys_recurses_under_prefix() -> None:
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="checkwise-test")
    svc = S3StorageService(bucket="checkwise-test", client=client)
    svc.save_bytes(storage_key="metadata_exports/acme/v1/latest_metadata.xlsx", data=b"a")
    svc.save_bytes(storage_key="metadata_exports/acme/v2/latest_metadata.xlsx", data=b"b")
    svc.save_bytes(storage_key="metadata_exports/otra/latest_metadata.xlsx", data=b"c")

    keys = svc.list_keys("metadata_exports/acme/")

    assert sorted(keys) == [
        "metadata_exports/acme/v1/latest_metadata.xlsx",
        "metadata_exports/acme/v2/latest_metadata.xlsx",
    ]
    assert svc.list_keys("metadata_exports/no-such-client/") == []


# ---------------------------------------------------------------------------
# 3. The mirror
# ---------------------------------------------------------------------------


@pytest.fixture()
def mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """S3-backed mirror over a tmp export root. Yields the moto-backed
    storage service so tests can assert on bucket contents directly."""
    export_root = tmp_path / "exports"
    export_root.mkdir()
    monkeypatch.setattr(metadata_store.settings, "METADATA_EXPORT_PATH", str(export_root))
    monkeypatch.setattr(metadata_store.settings, "STORAGE_BACKEND", "s3")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="checkwise-test")
        svc = S3StorageService(bucket="checkwise-test", client=client)
        monkeypatch.setattr(metadata_store, "get_storage_service", lambda: svc)
        yield export_root, svc


def test_export_storage_key_rejects_paths_outside_root(mirror) -> None:
    export_root, _ = mirror
    inside = export_root / "acme" / "latest_metadata.xlsx"
    outside = export_root.parent / "elsewhere.xlsx"
    assert metadata_store.export_storage_key(inside) == (
        "metadata_exports/acme/latest_metadata.xlsx"
    )
    assert metadata_store.export_storage_key(outside) is None


def test_persist_then_ensure_roundtrip_after_disk_wipe(mirror) -> None:
    """The deploy scenario: workbook written + mirrored, disk wiped,
    read path re-materializes the file from the mirror."""
    export_root, _ = mirror
    workbook = export_root / "acme" / "v1" / "latest_metadata.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"xlsx-bytes")

    metadata_store.persist_export(workbook)
    workbook.unlink()  # the "deploy" — ephemeral disk wiped
    assert not workbook.exists()

    restored = metadata_store.ensure_local_export(workbook)

    assert restored == workbook
    assert workbook.exists()
    assert workbook.read_bytes() == b"xlsx-bytes"


def test_ensure_local_export_miss_leaves_path_absent(mirror) -> None:
    export_root, _ = mirror
    never_written = export_root / "acme" / "ghost.xlsx"
    result = metadata_store.ensure_local_export(never_written)
    assert result == never_written
    assert not never_written.exists()


def test_sync_client_latest_exports_materializes_only_latest(mirror) -> None:
    """Post-deploy master rebuild: every latest_metadata.xlsx for the
    client comes back; historical per-document workbooks do not."""
    export_root, svc = mirror
    svc.save_bytes(
        storage_key="metadata_exports/acme/v1/latest_metadata.xlsx", data=b"v1"
    )
    svc.save_bytes(
        storage_key="metadata_exports/acme/v2/latest_metadata.xlsx", data=b"v2"
    )
    svc.save_bytes(
        storage_key="metadata_exports/acme/v1/sub_doc_metadata.xlsx", data=b"hist"
    )
    svc.save_bytes(
        storage_key="metadata_exports/otra/v1/latest_metadata.xlsx", data=b"other"
    )

    metadata_store.sync_client_latest_exports("acme")

    assert (export_root / "acme" / "v1" / "latest_metadata.xlsx").read_bytes() == b"v1"
    assert (export_root / "acme" / "v2" / "latest_metadata.xlsx").read_bytes() == b"v2"
    assert not (export_root / "acme" / "v1" / "sub_doc_metadata.xlsx").exists()
    assert not (export_root / "otra").exists()


def test_sync_rejects_traversal_keys_and_writes_nothing_outside_root(mirror) -> None:
    """CW-FILE-001 — a mirror key with ``..`` segments must NOT be written
    outside the export root, while a benign in-root key still materializes."""
    export_root, svc = mirror
    svc.save_bytes(
        storage_key="metadata_exports/acme/v1/latest_metadata.xlsx", data=b"ok"
    )
    # A corrupt/attacker-planted key that resolves above the export root.
    svc.save_bytes(
        storage_key="metadata_exports/acme/../../escape/latest_metadata.xlsx",
        data=b"evil",
    )

    metadata_store.sync_client_latest_exports("acme")

    # The benign slot came back.
    assert (
        export_root / "acme" / "v1" / "latest_metadata.xlsx"
    ).read_bytes() == b"ok"
    # Nothing was written outside the root.
    escape = export_root.parent / "escape" / "latest_metadata.xlsx"
    assert not escape.exists()
    assert not (export_root.parent / "escape").exists()


def test_contained_local_path_rejects_escapes(mirror) -> None:
    export_root, _ = mirror
    root = metadata_store._export_root()
    assert metadata_store._contained_local_path(
        "metadata_exports/acme/v1/latest_metadata.xlsx"
    ) == (root / "acme" / "v1" / "latest_metadata.xlsx")
    assert (
        metadata_store._contained_local_path(
            "metadata_exports/acme/../../escape/x.xlsx"
        )
        is None
    )
    assert (
        metadata_store._contained_local_path("metadata_exports/../escape.xlsx")
        is None
    )
    assert (
        metadata_store._contained_local_path("other_prefix/latest_metadata.xlsx")
        is None
    )


def test_mirror_is_noop_on_local_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On the local backend the disk IS the durable store — no mirror
    traffic, and a missing file stays missing (regular 404 path)."""
    export_root = tmp_path / "exports"
    export_root.mkdir()
    monkeypatch.setattr(metadata_store.settings, "METADATA_EXPORT_PATH", str(export_root))
    monkeypatch.setattr(metadata_store.settings, "STORAGE_BACKEND", "local")

    def _explode() -> None:  # storage must never be touched
        raise AssertionError("local backend must not reach the storage service")

    monkeypatch.setattr(metadata_store, "get_storage_service", _explode)

    workbook = export_root / "acme" / "latest_metadata.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"x")

    metadata_store.persist_export(workbook)
    metadata_store.sync_client_latest_exports("acme")
    missing = export_root / "acme" / "missing.xlsx"
    assert metadata_store.ensure_local_export(missing) == missing
    assert not missing.exists()
