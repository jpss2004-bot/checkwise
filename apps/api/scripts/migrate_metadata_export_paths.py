"""Re-key the metadata-export tree from ``<name-slug>/`` to ``<name-slug>-<id>/``.

Historically the metadata-export tree (per-slot tables + the per-client master)
was keyed ONLY on ``_slug(client.name)``. ``Client.name`` has no DB uniqueness
(only ``rfc`` is unique), so two clients whose names slugify identically shared
one ``metadata_exports/<slug>/...`` subtree — the master rebuild then aggregated
both tenants' rows into a single workbook that ``/client/metadata/download``
served cross-tenant. The fix (see ``app.services.metadata_export``) suffixes the
immutable, unique ``client.id`` onto the segment:

    metadata_exports/<name-slug>/...        →  metadata_exports/<name-slug>-<id>/...

Exports written BEFORE the fix still live under the old ``<slug>/`` paths and
would orphan (the new code never looks there again). This one-off relocates each
existing old tree to its new id-suffixed home, on the local filesystem and — when
``STORAGE_BACKEND=s3`` — the R2 mirror.

DARK + DRY-RUN BY DEFAULT. Nothing moves until you pass ``--apply``. The default
run only prints what it WOULD move.

Usage::

    cd apps/api
    .venv/bin/python -m scripts.migrate_metadata_export_paths            # dry-run (default)
    .venv/bin/python -m scripts.migrate_metadata_export_paths --apply    # actually move
    .venv/bin/python -m scripts.migrate_metadata_export_paths --apply --client-id <uuid>
    .venv/bin/python -m scripts.migrate_metadata_export_paths --apply --delete-old

By default the old tree is COPIED (left in place) so the migration is reversible;
pass ``--delete-old`` to remove the old tree/keys after a verified copy.

IMPORTANT: to migrate the durable R2 mirror on prod the process MUST run with
``STORAGE_BACKEND=s3`` (``.env.production`` omits it). Without it only the local
filesystem tree is considered — which is ephemeral on Render, so the S3 pass is
the one that matters in production.

This script is intentionally NOT wired to any endpoint or cron — run it once, by
hand, after the path-keying fix deploys.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.models import Client  # noqa: E402
from app.services.metadata_export import _client_dir_segment, _slug  # noqa: E402
from app.services.metadata_store import _PREFIX, mirror_enabled  # noqa: E402
from app.services.storage import get_storage_service  # noqa: E402


def _export_root() -> Path:
    return Path(settings.METADATA_EXPORT_PATH).expanduser().resolve()


def _migrate_local(
    *,
    old_segment: str,
    new_segment: str,
    apply: bool,
    delete_old: bool,
    log,
) -> bool:
    """Relocate one client's local export tree. Returns True if work was found."""
    root = _export_root()
    old_dir = root / old_segment
    new_dir = root / new_segment
    if not old_dir.exists():
        return False
    if old_dir == new_dir:
        # Already id-suffixed (segment unchanged) — nothing to do.
        return False
    if new_dir.exists():
        log(
            f"  [local] SKIP {old_segment}/ → {new_segment}/ "
            f"(destination already exists — leaving old tree in place)"
        )
        return True
    file_count = sum(1 for _ in old_dir.rglob("*") if _.is_file())
    if not apply:
        log(
            f"  [local] would move {old_segment}/ → {new_segment}/ "
            f"({file_count} file(s))"
        )
        return True
    new_dir.parent.mkdir(parents=True, exist_ok=True)
    # Copy (not move) by default so the migration is reversible; the old tree
    # is removed only when --delete-old is given.
    shutil.copytree(old_dir, new_dir)
    log(f"  [local] copied {old_segment}/ → {new_segment}/ ({file_count} file(s))")
    if delete_old:
        shutil.rmtree(old_dir)
        log(f"  [local] removed old tree {old_segment}/")
    return True


def _migrate_mirror(
    *,
    old_segment: str,
    new_segment: str,
    apply: bool,
    delete_old: bool,
    log,
) -> bool:
    """Relocate one client's R2 mirror keys. Returns True if work was found."""
    if not mirror_enabled():
        return False
    if old_segment == new_segment:
        return False
    storage = get_storage_service()
    old_prefix = f"{_PREFIX}/{old_segment}/"
    new_prefix = f"{_PREFIX}/{new_segment}/"
    try:
        old_keys = storage.list_keys(old_prefix)
    except Exception as exc:  # noqa: BLE001 — surfaced, not fatal for other clients
        log(f"  [s3]    ERROR listing {old_prefix}: {exc.__class__.__name__}: {exc}")
        return False
    if not old_keys:
        return False
    # Don't clobber an already-migrated mirror.
    try:
        existing_new = storage.list_keys(new_prefix)
    except Exception:  # noqa: BLE001
        existing_new = []
    if existing_new:
        log(
            f"  [s3]    SKIP {old_prefix} → {new_prefix} "
            f"(destination prefix already populated)"
        )
        return True
    if not apply:
        log(f"  [s3]    would copy {len(old_keys)} object(s) {old_prefix} → {new_prefix}")
        return True
    copied = 0
    for key in old_keys:
        suffix = key[len(old_prefix):]
        new_key = f"{new_prefix}{suffix}"
        try:
            local = storage.open_for_read(key)
            storage.save_bytes(
                storage_key=new_key,
                data=Path(local).read_bytes(),
                content_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )
            copied += 1
        except Exception as exc:  # noqa: BLE001 — per-object, keep going
            log(f"  [s3]    FAILED copy {key}: {exc.__class__.__name__}: {exc}")
    log(f"  [s3]    copied {copied}/{len(old_keys)} object(s) {old_prefix} → {new_prefix}")
    if delete_old and copied == len(old_keys):
        for key in old_keys:
            storage.delete(key)
        log(f"  [s3]    removed {len(old_keys)} old object(s) under {old_prefix}")
    elif delete_old:
        log(
            f"  [s3]    NOT deleting old keys — only {copied}/{len(old_keys)} "
            f"copied cleanly"
        )
    return True


def migrate(
    *,
    apply: bool,
    delete_old: bool,
    client_id: str | None,
    log,
) -> None:
    backend = (settings.STORAGE_BACKEND or "local").strip().lower()
    mode = "APPLY" if apply else "DRY-RUN"
    log(f"metadata-export path migration [{mode}] — STORAGE_BACKEND={backend}")
    log(f"export root: {_export_root()}")
    if not mirror_enabled():
        log("(S3 mirror disabled — only the local filesystem tree is considered)")
    log("")

    db = db_session.SessionLocal()
    try:
        stmt = select(Client).order_by(Client.created_at)
        if client_id:
            stmt = stmt.where(Client.id == client_id)
        clients = list(db.scalars(stmt))
    finally:
        db.close()

    # Two clients can share the same old slug — that collision is the very bug
    # this re-keying fixes. Only the FIRST client (by created_at) can own the
    # ambiguous old tree; the rest are flagged so a human resolves them.
    seen_old: dict[str, str] = {}
    touched = 0
    for client in clients:
        old_segment = _slug(client.name)
        new_segment = _client_dir_segment(client)
        clash = seen_old.get(old_segment)
        if clash is not None:
            log(
                f"{client.name} ({client.id}): AMBIGUOUS old slug "
                f"'{old_segment}/' also claimed by {clash} — manual review "
                f"needed; skipping automatic move."
            )
            continue
        seen_old[old_segment] = client.id

        local_work = _migrate_local(
            old_segment=old_segment,
            new_segment=new_segment,
            apply=apply,
            delete_old=delete_old,
            log=log,
        )
        mirror_work = _migrate_mirror(
            old_segment=old_segment,
            new_segment=new_segment,
            apply=apply,
            delete_old=delete_old,
            log=log,
        )
        if local_work or mirror_work:
            touched += 1
            log(f"  ↳ {client.name} ({client.id})  {old_segment}/ → {new_segment}/")
            log("")

    verb = "moved" if apply else "would move"
    log(f"done — {verb} export trees for {touched} client(s).")
    if not apply:
        log("DRY-RUN: re-run with --apply to perform the migration.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Relocate metadata-export trees from <name-slug>/ to "
            "<name-slug>-<client_id>/ (local FS + R2 mirror). Dry-run by default."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move the trees (default: dry-run, prints only).",
    )
    parser.add_argument(
        "--delete-old",
        action="store_true",
        help=(
            "After a clean copy, remove the old <name-slug>/ tree/keys "
            "(default: copy + leave old in place so the move is reversible)."
        ),
    )
    parser.add_argument(
        "--client-id",
        default=None,
        help="Limit the migration to a single client id (default: all clients).",
    )
    args = parser.parse_args()

    migrate(
        apply=args.apply,
        delete_old=args.delete_old,
        client_id=args.client_id,
        log=print,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
