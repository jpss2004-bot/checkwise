"""Backfill AI shadow analysis for already-stored documents.

Shadow analysis (the Claude "pre-validación / detección con IA" that powers the
reviewer Veredicto card) only runs as a BackgroundTask at upload time. Documents
that were seeded, imported, or uploaded while the feature was gated off therefore
have empty ``shadow_*`` columns and show "Sin analizar" in the Mesa de Revisión.
This re-runs ``run_shadow_analysis`` over existing documents, pulling each PDF
from storage on demand — no re-upload, no status change.

WHAT IT DOES NOT DO: it never mutates Submission/Document status, never notifies a
provider, and never auto-approves (it asserts the auto-approval engine is dark
before it will run). Shadow analysis only writes reviewer-facing ``shadow_*``
columns on ``DocumentInspection``.

Idempotent + resumable: a document whose inspection already has a clean shadow
result (``shadow_provider_id`` set AND ``shadow_error`` NULL) is skipped. Rows
that errored — including the ``daily_cap_exceeded`` poison state — are retried by
default, so re-invoking simply continues where it stopped. Dry-run by default;
pass --apply to execute.

WHERE TO RUN: the script reads its gating config from ``settings`` (env + .env),
so it must run in an environment whose env matches production — easiest is the
Render service Shell (env already correct). Run locally only if you export the
same DOCUMENT_ANALYSIS_*, ANTHROPIC_API_KEY, DATABASE_URL, AWS_*, STORAGE_*
values; otherwise the provider resolves to "disabled" and preflight aborts (by
design).

Usage:
  cd apps/api
  .venv/bin/python -m scripts.reprocess_shadow_analysis                 # dry-run (default client)
  .venv/bin/python -m scripts.reprocess_shadow_analysis --limit 25 --apply
  .venv/bin/python -m scripts.reprocess_shadow_analysis \
      --client-id 2d8a10db-1855-570a-87a0-04d2d84b9354 --vendor-id <id> --apply
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import or_  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Client, Document, DocumentInspection, Submission  # noqa: E402
from app.services.document_analysis.factory import (  # noqa: E402
    build_document_analysis_provider,
)
from app.services.document_analysis.shadow_runner import (  # noqa: E402
    _pilot_allowlist,
    run_shadow_analysis,
)
from app.services.storage import get_storage_service  # noqa: E402

# Default flagship demo client (Corporativo Industrial Anáhuac).
DEFAULT_CLIENT_ID = "2d8a10db-1855-570a-87a0-04d2d84b9354"

# Mirror of shadow_runner's escalation trigger for a *cost estimate only*: these
# risk levels always escalate to the stronger (Sonnet) tier. Kept local so the
# script does not couple to a private symbol; estimate is advisory.
_HIGH_STAKES_RISK_LEVELS = {"alto", "critico", "crítico"}


class PreflightError(RuntimeError):
    """A gate that would make the backfill silently no-op or unsafe."""


def _download_with_retry(storage, storage_key: str, *, attempts: int = 4):  # noqa: ANN001
    """Materialize a PDF from storage, retrying transient connectivity drops.

    R2/S3 downloads over a long sequential run can hit transient "Could not
    connect to the endpoint URL" failures; a doc that fails all attempts is
    left eligible (no shadow row written) so a later run retries it.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return storage.open_for_read(storage_key)
        except Exception as exc:  # noqa: BLE001 — retry transient storage errors
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(2.0 * (attempt + 1))  # 2s, 4s, 6s backoff
    raise last_exc  # type: ignore[misc]


def _preflight(client_id: str) -> dict:
    """Assert every condition that would otherwise silently waste the run.

    Returns a dict of resolved facts for printing. Raises PreflightError on any
    blocking condition — these are exactly the traps (provider disabled, pilot
    allowlist excludes the org, auto-approval live) that make a backfill look
    successful while doing nothing or mutating prod.
    """
    facts: dict = {}

    # 1. Provider must be the real Anthropic backend, not the "disabled" default
    #    (→ factory returns None → run_shadow_analysis bare-returns) and not the
    #    heuristic fallback (→ no AI, just the regex baseline).
    provider_name = (settings.DOCUMENT_ANALYSIS_PROVIDER or "disabled").strip().lower()
    facts["DOCUMENT_ANALYSIS_PROVIDER"] = provider_name
    if provider_name not in {"anthropic", "shadow"}:
        raise PreflightError(
            f"DOCUMENT_ANALYSIS_PROVIDER={provider_name!r}; need 'anthropic'. "
            "The AI provider is off in this environment — nothing would run."
        )
    try:
        provider = build_document_analysis_provider(tier="triage")
    except Exception as exc:  # noqa: BLE001
        raise PreflightError(f"Provider build failed: {exc}") from exc
    if provider is None:
        raise PreflightError("Provider resolved to None (disabled).")
    facts["triage_provider_id"] = provider.provider_id
    if "heuristic" in provider.provider_id.lower():
        raise PreflightError(
            f"Triage provider is the heuristic baseline ({provider.provider_id}); "
            "ANTHROPIC_API_KEY is likely missing — no real AI would run."
        )
    facts["triage_model"] = settings.DOCUMENT_ANALYSIS_TRIAGE_MODEL
    facts["escalation_model"] = settings.DOCUMENT_ANALYSIS_MODEL

    # 2. Pilot allowlist must not silently exclude this org (the original bug).
    allowlist = _pilot_allowlist()
    facts["pilot_allowlist"] = sorted(allowlist) or "(empty → all orgs in scope)"
    if allowlist and client_id not in allowlist:
        raise PreflightError(
            f"client_id {client_id} is NOT in DOCUMENT_ANALYSIS_PILOT_ORG_IDS "
            f"({sorted(allowlist)}). Every call would silently no-op. Add it to "
            "the allowlist (or clear the allowlist) before backfilling."
        )

    # 3. Auto-approval must be dark — a backfill must never mass-transition
    #    Submission/Document status or fire provider notifications on prod.
    auto_enabled = bool(settings.AUTO_APPROVE_ENABLED)
    unlocked = (settings.AUTO_APPROVE_UNLOCKED_REQUIREMENT_CODES or "").strip()
    facts["AUTO_APPROVE_ENABLED"] = auto_enabled
    facts["AUTO_APPROVE_UNLOCKED_REQUIREMENT_CODES"] = unlocked or "(empty)"
    if auto_enabled and unlocked:
        raise PreflightError(
            "AUTO_APPROVE_ENABLED is True AND requirement codes are unlocked — "
            "a backfill could auto-approve documents and notify providers. "
            "Refusing to run. Disable auto-approval for the backfill window."
        )

    facts["STORAGE_BACKEND"] = (settings.STORAGE_BACKEND or "local").strip().lower()
    facts["EXPEDIENTE_ENABLED"] = bool(settings.DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED)
    # A1 triage-skip — when ON, run_shadow_analysis re-skips heuristically
    # clean+aligned, never-analyzed docs in-process instead of calling the AI,
    # so a backfill silently produces 0 real triage calls on that subset (and
    # re-emits a skip event). Surfaced (not a hard block: errored rows — which
    # have shadow_completed_at set — are NOT skip-eligible and still reprocess).
    facts["DOCUMENT_ANALYSIS_TRIAGE_SKIP_ENABLED"] = bool(
        settings.DOCUMENT_ANALYSIS_TRIAGE_SKIP_ENABLED
    )
    return facts


def _resolve_items(db, args) -> tuple[list[dict], list[str]]:
    """Resolve every shadow-analysis arg tuple inside ONE short read txn.

    Returns (items, skipped_notes). Each item is a plain dict of primitives plus
    the storage_key — no ORM object escapes the session, so the loop can run for
    minutes without pinning a connection idle-in-transaction.
    """
    # Eligibility: not-yet-analyzed OR previously errored (so cap-poisoned /
    # transient-failure rows are retried). --include-done forces everything;
    # --skip-errored restricts to never-analyzed only.
    if args.include_done:
        eligibility = None
    elif args.skip_errored:
        eligibility = DocumentInspection.shadow_provider_id.is_(None)
    else:
        eligibility = or_(
            DocumentInspection.shadow_provider_id.is_(None),
            DocumentInspection.shadow_error.isnot(None),
        )

    q = (
        db.query(DocumentInspection, Document, Submission)
        .join(Document, DocumentInspection.document_id == Document.id)
        .join(Submission, Document.submission_id == Submission.id)
        .options(
            joinedload(Submission.vendor),
            joinedload(Submission.institution),
            joinedload(Submission.period),
            joinedload(Submission.requirement),
            joinedload(Submission.client),
        )
        .filter(Submission.client_id == args.client_id)
    )
    if eligibility is not None:
        q = q.filter(eligibility)
    if args.vendor_id:
        q = q.filter(Submission.vendor_id == args.vendor_id)
    if args.requirement_code:
        q = q.filter(Submission.requirement_code.in_(args.requirement_code))
    if args.status:
        q = q.filter(Submission.status.in_(args.status))
    q = q.order_by(Submission.created_at.asc())
    if args.limit:
        q = q.limit(args.limit)

    items: list[dict] = []
    skipped: list[str] = []
    for _inspection, document, submission in q.all():
        req = submission.requirement
        vendor = submission.vendor
        client = submission.client
        institution = submission.institution
        period = submission.period

        # period_code is Period.code (human-readable), NEVER period_key.
        period_code = period.code if period else submission.period_key
        requirement_code = (req.code if req else None) or submission.requirement_code
        requirement_name = (req.name if req else None) or ""
        institution_code = institution.code if institution else None
        risk_level = req.risk_level if req else None

        # Skip rows missing a join the runner needs, rather than passing None
        # and persisting a junk "done" result.
        missing = [
            label
            for label, value in (
                ("storage_key", document.storage_key),
                ("institution_code", institution_code),
                ("period_code", period_code),
                ("requirement_name", requirement_name),
                ("vendor.rfc", vendor.rfc if vendor else None),
            )
            if not value
        ]
        if missing:
            skipped.append(f"{document.id} (missing {', '.join(missing)})")
            continue

        items.append(
            {
                "storage_key": document.storage_key,
                "risk_level": (risk_level or "").strip().lower(),
                "args": {
                    "document_id": document.id,
                    "submission_id": submission.id,
                    "requirement_code": requirement_code,
                    "requirement_name": requirement_name,
                    "institution_code": institution_code,
                    "period_code": period_code,
                    "org_id": client.id if client else args.client_id,
                    "requirement_risk_level": risk_level,
                    "expected_provider_rfc": vendor.rfc if vendor else None,
                    "expected_provider_name": vendor.name if vendor else None,
                    "expected_client_name": client.name if client else None,
                    "expected_client_rfc": client.rfc if client else None,
                },
            }
        )
    return items, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--vendor-id", default=None)
    parser.add_argument(
        "--requirement-code", action="append", default=None, help="repeatable"
    )
    parser.add_argument(
        "--status", action="append", default=None, help="submission status; repeatable"
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--include-done",
        action="store_true",
        help="re-run even documents that already have a clean shadow result",
    )
    parser.add_argument(
        "--skip-errored",
        action="store_true",
        help="do NOT retry previously-errored rows (default retries them)",
    )
    parser.add_argument(
        "--cap-triage",
        type=int,
        default=0,
        help="override DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG for this run "
        "(0=disabled, default; prevents the 200/day cap from stranding rows)",
    )
    parser.add_argument(
        "--cap-escalation",
        type=int,
        default=None,
        help="override the escalation cap (default: leave env value, usually 50, "
        "so expensive Sonnet re-runs self-limit on the first pass)",
    )
    parser.add_argument(
        "--sleep", type=float, default=0.4, help="seconds between calls (pacing)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="run analysis (default is a dry-run that only reports + estimates)",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("SHADOW ANALYSIS BACKFILL —", "APPLY" if args.apply else "DRY-RUN")
    print("=" * 72)

    # --- Preflight (always, both dry-run and apply) -----------------------
    try:
        facts = _preflight(args.client_id)
    except PreflightError as exc:
        print(f"\n  ABORT (preflight): {exc}\n")
        return 2
    print("\nResolved config:")
    for key, value in facts.items():
        print(f"  {key:38} = {value}")

    if facts.get("DOCUMENT_ANALYSIS_TRIAGE_SKIP_ENABLED"):
        print(
            "\n  WARNING: DOCUMENT_ANALYSIS_TRIAGE_SKIP_ENABLED is ON.\n"
            "  Heuristically clean+aligned, never-analyzed docs will be RE-SKIPPED\n"
            "  in-process (no real AI call; another 'shadow_analysis_skipped' event)\n"
            "  — the 'Triage calls (Haiku)' estimate below OVERSTATES real calls on\n"
            "  that subset. To force a real AI backfill on skip-eligible docs,\n"
            "  disable the flag for the backfill window (errored rows reprocess\n"
            "  regardless)."
        )

    # --- Enumerate (one short read transaction) ---------------------------
    db = SessionLocal()
    try:
        client = db.get(Client, args.client_id)
        if client is None:
            print(f"\n  ABORT: client_id {args.client_id} not found.\n")
            return 2
        print(f"\nClient: {client.name} ({client.id})")
        items, skipped = _resolve_items(db, args)
    finally:
        db.close()

    high_stakes = sum(1 for it in items if it["risk_level"] in _HIGH_STAKES_RISK_LEVELS)
    print(f"\nEligible documents : {len(items)}")
    print(f"Skipped (bad joins): {len(skipped)}")
    for note in skipped[:10]:
        print(f"    - {note}")
    if len(skipped) > 10:
        print(f"    … and {len(skipped) - 10} more")

    print("\nCost estimate (worst case):")
    print(f"  Triage calls (Haiku)      : {len(items)}")
    print(
        f"  Escalation calls (Sonnet) : {high_stakes} (high-stakes floor) "
        f"→ up to {len(items)} (ceiling)"
    )
    eff_triage = args.cap_triage
    eff_escal = (
        args.cap_escalation
        if args.cap_escalation is not None
        else settings.DOCUMENT_ANALYSIS_ESCALATION_DAILY_CAP_PER_ORG
    )
    print(
        f"  Effective caps this run   : triage={eff_triage or 'disabled'} "
        f"escalation={eff_escal or 'disabled'}"
    )

    if items:
        print("\nSample resolved args (proves joins succeed):")
        for it in items[:3]:
            a = it["args"]
            print(
                f"  - {a['requirement_code']} | {a['institution_code']} | "
                f"{a['period_code']} | risk={a['requirement_risk_level']} | "
                f"prov={a['expected_provider_rfc']}"
            )

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to execute.\n")
        return 0

    if not items:
        print("\nNothing to do.\n")
        return 0

    # --- Apply: in-process cap overrides, then the loop -------------------
    settings.DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG = args.cap_triage
    if args.cap_escalation is not None:
        settings.DOCUMENT_ANALYSIS_ESCALATION_DAILY_CAP_PER_ORG = args.cap_escalation

    storage = get_storage_service()
    is_s3 = (settings.STORAGE_BACKEND or "local").strip().lower() == "s3"
    done = errored = 0
    started = time.monotonic()
    print(f"\nProcessing {len(items)} documents…\n")

    for idx, it in enumerate(items, start=1):
        materialized_path = None
        try:
            materialized_path = _download_with_retry(storage, it["storage_key"])
            # run_shadow_analysis opens its own session and never raises.
            run_shadow_analysis(pdf_path=str(materialized_path), **it["args"])
            done += 1
        except Exception as exc:  # noqa: BLE001 — keep the batch going
            errored += 1
            print(f"  ! {it['args']['document_id']}: {exc}")
        finally:
            # Clean up S3 temp downloads; NEVER unlink the local durable path.
            if is_s3 and materialized_path is not None:
                try:
                    materialized_path.unlink(missing_ok=True)
                except OSError:
                    pass
        if idx % 25 == 0 or idx == len(items):
            elapsed = time.monotonic() - started
            print(
                f"  [{idx}/{len(items)}] done={done} errored={errored} "
                f"elapsed={elapsed:.0f}s"
            )
        if args.sleep:
            time.sleep(args.sleep)

    print(
        f"\nFinished: {done} analyzed, {errored} errored, "
        f"{time.monotonic() - started:.0f}s elapsed."
    )
    print(
        "Note: a 'daily_cap_exceeded' or transient error leaves the row eligible "
        "for retry on the next run.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
