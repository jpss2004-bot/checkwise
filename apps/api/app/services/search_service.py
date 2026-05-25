"""Cross-role submission search.

One small service that powers the global search bar in every shell
(provider, client, admin). Detects the query type from its shape and
runs a single SQL query with the matching predicate. Results are
scoped at the call site so each role only ever sees their own data.

Detection rules:
    * RFC      — ``[A-Z&Ñ]{3,4}\\d{6}[A-Z0-9]{3}``, case-insensitive
                  (matches both ``Vendor.rfc`` and ``Client.rfc``).
    * Periodo  — ``YYYY-Mxx`` / ``YYYY-Bx`` / ``YYYY-Qx`` / ``YYYY-A``
                  (matches the denormalized ``Submission.period_key``).
    * Folio    — anything else, treated as a case-insensitive substring
                  match against ``Contract.repse_folio`` plus the
                  submission ID prefix so reviewers can paste a
                  partial UUID from a ticket.

The point of detecting first (rather than ORing every column) is so a
short string like "AB" doesn't accidentally match thousands of RFCs;
folio queries already cap themselves with ILIKE substrings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Client,
    Contract,
    Institution,
    Period,
    Requirement,
    Submission,
    Vendor,
)

# ── Pattern detection ───────────────────────────────────────────────

# Mexican RFC: 12 (persona moral) or 13 (persona física) alphanumerics
# split into ``LLLL DDDDDD AAA``. Allow ``Ñ`` and ``&`` per the SAT
# spec. Case-insensitive at the call site.
_RFC_RE = re.compile(r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$", re.IGNORECASE)

# Canonical period keys mirror the catalog:
#   YYYY-Mxx (monthly)   YYYY-Bx (bimonthly)
#   YYYY-Qx (quarterly)  YYYY-A   (annual)
# Plus a forgiving ``YYYY-MM`` variant so a user typing "2026-05" is
# treated as the M05 key and we let the SQL match handle the rest.
_PERIOD_RE = re.compile(
    r"^\d{4}-(?:M\d{2}|B[1-6]|Q[1-3]|A|\d{1,2})$", re.IGNORECASE
)

QueryType = Literal["rfc", "period", "folio"]


def detect_query_type(query: str) -> QueryType:
    """Return the detected query type from the input shape.

    Falls back to ``"folio"`` whenever the input doesn't match the RFC
    or period regex — the folio path runs as a permissive ILIKE so a
    miscategorised query degrades to a substring search rather than to
    no results.
    """

    q = query.strip()
    if not q:
        return "folio"
    if _RFC_RE.match(q):
        return "rfc"
    if _PERIOD_RE.match(q):
        return "period"
    return "folio"


def _normalize_period(query: str) -> str:
    """Normalize a user-typed period to the catalog's ``YYYY-Mxx`` form.

    ``2026-5`` and ``2026-05`` both map to ``2026-M05`` so a single
    query can hit Submission.period_key cleanly. Non-monthly keys
    (``2026-B1``, ``2026-Q1``, ``2026-A``) are uppercased and returned
    as-is so they match catalog data exactly.
    """

    q = query.strip().upper()
    if "-" not in q:
        return q
    year, rest = q.split("-", 1)
    if rest.startswith(("M", "B", "Q", "A")):
        return f"{year}-{rest}"
    # Numeric tail: e.g. "2026-5" → "2026-M05"
    if rest.isdigit():
        return f"{year}-M{rest.zfill(2)}"
    return q


# ── Result shape ────────────────────────────────────────────────────


@dataclass(frozen=True)
class SearchHit:
    submission_id: str
    vendor_id: str
    vendor_name: str
    vendor_rfc: str | None
    client_id: str
    client_name: str
    client_rfc: str | None
    period_key: str | None
    institution_code: str | None
    institution_label: str | None
    requirement_name: str | None
    status: str
    contract_folio: str | None
    matched_by: QueryType
    created_at: str


# ── Core search ─────────────────────────────────────────────────────


def search_submissions(
    db: Session,
    query: str,
    *,
    client_ids: list[str] | None = None,
    vendor_ids: list[str] | None = None,
    limit: int = 50,
) -> list[SearchHit]:
    """Return submissions matching ``query`` under the supplied scope.

    ``client_ids`` and ``vendor_ids`` work as positive scopes: ``None``
    means "no restriction on this axis" and a list narrows the result
    to those values. Admin callers pass ``None`` for both. Client
    callers pass a list of client_ids they own. Provider callers pass
    a single-element vendor_ids list for the active workspace.

    The query is parsed once and only one predicate is added to the SQL
    statement — this keeps the planner from having to OR three
    different access paths together. Edge cases (empty query string,
    impossible scope) short-circuit to an empty list so the caller
    never has to special-case "no results".
    """

    if not query.strip():
        return []

    qtype = detect_query_type(query)

    stmt = (
        select(Submission, Vendor, Client, Period, Institution, Requirement, Contract)
        .join(Vendor, Submission.vendor_id == Vendor.id)
        .join(Client, Submission.client_id == Client.id)
        .join(Period, Submission.period_id == Period.id)
        .join(Institution, Submission.institution_id == Institution.id)
        .join(Requirement, Submission.requirement_id == Requirement.id)
        .outerjoin(Contract, Submission.contract_id == Contract.id)
        .order_by(Submission.created_at.desc())
        .limit(limit)
    )

    if qtype == "rfc":
        rfc = query.strip().upper()
        stmt = stmt.where(or_(Vendor.rfc == rfc, Client.rfc == rfc))
    elif qtype == "period":
        period_key = _normalize_period(query)
        stmt = stmt.where(Submission.period_key == period_key)
    else:  # folio
        like = f"%{query.strip()}%"
        # Limit folio search to fields a public-facing user is plausibly
        # quoting from. Submission.id ILIKE keeps reviewers' "paste the
        # ticket UUID" workflow working without a separate lookup.
        stmt = stmt.where(
            or_(
                Contract.repse_folio.ilike(like),
                Submission.id.ilike(like),
            )
        )

    if client_ids is not None:
        if not client_ids:
            return []
        stmt = stmt.where(Submission.client_id.in_(client_ids))
    if vendor_ids is not None:
        if not vendor_ids:
            return []
        stmt = stmt.where(Submission.vendor_id.in_(vendor_ids))

    rows = db.execute(stmt).all()

    hits: list[SearchHit] = []
    for sub, vendor, client, period, institution, requirement, contract in rows:
        hits.append(
            SearchHit(
                submission_id=sub.id,
                vendor_id=vendor.id,
                vendor_name=vendor.name,
                vendor_rfc=vendor.rfc,
                client_id=client.id,
                client_name=client.name,
                client_rfc=client.rfc,
                period_key=sub.period_key or period.period_key,
                institution_code=institution.code,
                institution_label=institution.name,
                requirement_name=requirement.name,
                status=sub.status,
                contract_folio=contract.repse_folio if contract else None,
                matched_by=qtype,
                created_at=sub.created_at.isoformat(),
            )
        )
    return hits
