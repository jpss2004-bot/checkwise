"""Durable mirror for metadata-export workbooks.

The XLSX exports (per-slot tables + the client master) are written under
``settings.METADATA_EXPORT_PATH`` on local disk. On Render that disk is
EPHEMERAL — every deploy or restart wipes it, which used to 404 the
admin/client metadata downloads and, worse, made the next master rebuild
(which rglobs the local tree) silently produce a master containing only
the slots uploaded since the deploy — and then overwrite the previous,
complete master with it.

This module mirrors the export tree into the object-storage backend
(Cloudflare R2 in prod) under ``metadata_exports/...`` keys:

- :func:`persist_export` — after writing a workbook locally, copy it to
  the mirror. Best-effort: a mirror failure must never block an upload.
- :func:`ensure_local_export` — before reading/serving a workbook,
  re-materialize it from the mirror when the local copy is missing.
- :func:`sync_client_latest_exports` — before a master rebuild, pull
  down every ``latest_metadata.xlsx`` for the client so the rebuild
  sees the full slot set, not just the post-deploy uploads.

On the local backend all of these are no-ops: the disk IS the durable
store there, and mirroring onto the same disk would only duplicate
files. The local tree always remains the read path — the mirror is a
recovery source, not a second source of truth.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.services.storage import get_storage_service

logger = logging.getLogger("checkwise.metadata_store")

_PREFIX = "metadata_exports"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def mirror_enabled() -> bool:
    """True when a durable object-storage mirror backs the export tree."""
    return (settings.STORAGE_BACKEND or "local").strip().lower() == "s3"


def _export_root() -> Path:
    return Path(settings.METADATA_EXPORT_PATH).expanduser().resolve()


def export_storage_key(path: Path) -> str | None:
    """Mirror key for ``path``, or ``None`` when it sits outside the
    export root (the same containment rule the download endpoints
    enforce — nothing outside the tree ever reaches the mirror)."""
    try:
        rel = path.expanduser().resolve().relative_to(_export_root())
    except ValueError:
        return None
    return f"{_PREFIX}/{rel.as_posix()}"


def persist_export(path: Path) -> None:
    """Best-effort copy of a freshly written workbook into the mirror."""
    if not mirror_enabled():
        return
    key = export_storage_key(path)
    if key is None or not path.exists():
        return
    try:
        get_storage_service().save_bytes(
            storage_key=key, data=path.read_bytes(), content_type=_XLSX_MIME
        )
    except Exception:  # noqa: BLE001 — telemetry only; never block the upload
        logger.exception("[metadata_store] mirror upload failed for %s", key)


def ensure_local_export(path: Path) -> Path:
    """Re-materialize ``path`` from the mirror when missing locally.

    Returns ``path`` unchanged either way — callers keep their existing
    ``path.exists()`` checks, which turn a miss (file absent from the
    mirror too) into the usual 404.
    """
    if path.exists() or not mirror_enabled():
        return path
    key = export_storage_key(path)
    if key is None:
        return path
    try:
        temp = get_storage_service().open_for_read(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Path(temp).read_bytes())
    except Exception:  # noqa: BLE001 — a miss is an expected outcome here
        logger.info("[metadata_store] no mirror copy for %s", key)
    return path


def sync_client_latest_exports(client_slug: str) -> None:
    """Materialize every ``latest_metadata.xlsx`` for one client.

    Called before :func:`app.services.metadata_export.\
rebuild_client_master_metadata_export` rglobs the local tree, so a
    post-deploy rebuild aggregates the complete slot set instead of
    clobbering the master with whatever uploaded since the restart.
    """
    if not mirror_enabled():
        return
    prefix = f"{_PREFIX}/{client_slug}/"
    try:
        keys = get_storage_service().list_keys(prefix)
    except Exception:  # noqa: BLE001 — degrade to local-only rebuild
        logger.exception("[metadata_store] mirror listing failed for %s", prefix)
        return
    root = _export_root()
    for key in keys:
        if not key.endswith("latest_metadata.xlsx"):
            continue
        local = root / key[len(_PREFIX) + 1 :]
        if not local.exists():
            ensure_local_export(local)
