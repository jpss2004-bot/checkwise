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
    * Name     — free text that reads like a company name (has a space
                  or no digit): accent-insensitive substring match on
                  ``Vendor.name`` / ``Client.name``. Deduplicated to one
                  row per vendor so typing a provider name returns a
                  clean provider list, not one row per submission. This
                  is the most common query for a cliente corporativo
                  monitoring a portfolio of providers.
    * Folio    — anything else (a folio code / UUID fragment), treated
                  as a case-insensitive substring match against
                  ``Contract.repse_folio`` plus the submission ID prefix
                  so reviewers can paste a partial UUID from a ticket.

Both the name and folio paths search names AND folio/UUID, so a
misclassified query degrades to a broader substring match rather than
to zero results. The point of detecting first (rather than ORing every
column blindly) is so a short string like "AB" doesn't accidentally
match thousands of RFCs, and so name matches can be deduped per vendor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.text_search import accent_ci_contains
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

# A REPSE folio / UUID fragment is a single token that contains a digit;
# a provider/client name has a space or is purely alphabetic. Used to
# route free text to the name path (the common case) vs the folio path.
_HAS_DIGIT_RE = re.compile(r"\d")

# Minimum term length for the leading-wildcard substring (name/folio) path.
# A 1-char ``%a%`` ILIKE cannot use any index and full-scans the entire
# submissions join on every keystroke (the documented "feels frozen" hot path
# and a cheap DoS lever for any authenticated admin/reviewer). 2 chars is the
# floor where the pg_trgm GIN index (migration 0055) becomes usable, since a
# trigram index needs at least a 3-gram to seed but degrades gracefully to a
# bounded recheck for 2-char patterns. The exact-match RFC and period paths are
# anchored and index-friendly, so they are NOT subject to this floor. Callers
# that pass a 1-char substring query get an empty result (the endpoints already
# render ``hits=[]`` as "no results"), matching the "type more" contract.
MIN_SUBSTRING_TERM_LEN = 2

QueryType = Literal["rfc", "period", "folio", "name"]


def detect_query_type(query: str) -> QueryType:
    """Return the detected query type from the input shape.

    Free text that reads like a company name (has a space or no digit)
    routes to ``"name"``; everything else that isn't an RFC/period falls
    to ``"folio"``. Both name and folio paths search names AND
    folio/UUID, so a miscategorised query degrades to a broader
    substring search rather than to no results.
    """

    q = query.strip()
    if not q:
        return "folio"
    if _RFC_RE.match(q):
        return "rfc"
    if _PERIOD_RE.match(q):
        return "period"
    if (" " in q) or (not _HAS_DIGIT_RE.search(q)):
        return "name"
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
    dialect = db.get_bind().dialect.name
    term = query.strip()

    # Short-circuit the leading-wildcard substring path for too-short terms.
    # ``name``/``folio`` both run ``%term%`` ILIKE, which cannot use a b-tree
    # index; a 1-char term would sequential-scan the whole submissions join.
    # The RFC/period paths are exact/anchored, so they are exempt. Returning
    # an empty list matches the endpoints' existing "no results" contract and
    # signals the UI to prompt for a longer query.
    if qtype in ("name", "folio") and len(term) < MIN_SUBSTRING_TERM_LEN:
        return []

    # Name queries dedupe to one row per vendor below, so over-fetch a
    # generous window first — otherwise a single chatty provider's recent
    # submissions could fill ``limit`` and crowd out every other match.
    fetch_limit = limit if qtype != "name" else min(max(limit * 10, 200), 1000)

    stmt = (
        select(Submission, Vendor, Client, Period, Institution, Requirement, Contract)
        .join(Vendor, Submission.vendor_id == Vendor.id)
        .join(Client, Submission.client_id == Client.id)
        .join(Period, Submission.period_id == Period.id)
        .join(Institution, Submission.institution_id == Institution.id)
        .join(Requirement, Submission.requirement_id == Requirement.id)
        .outerjoin(Contract, Submission.contract_id == Contract.id)
        .order_by(Submission.created_at.desc())
        .limit(fetch_limit)
    )

    if qtype == "rfc":
        rfc = term.upper()
        stmt = stmt.where(or_(Vendor.rfc == rfc, Client.rfc == rfc))
    elif qtype == "period":
        period_key = _normalize_period(query)
        stmt = stmt.where(Submission.period_key == period_key)
    else:  # name or folio — search provider/client names AND folio/UUID
        like = f"%{term}%"
        # Accent-insensitive name match (Spanish diacritics) plus the
        # folio + submission-id substrings a user might paste. Searching
        # both keeps a misclassified query from returning nothing.
        stmt = stmt.where(
            or_(
                accent_ci_contains(dialect, Vendor.name, term),
                accent_ci_contains(dialect, Client.name, term),
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

    # For a name search the user wants the matching PROVIDERS, not every
    # submission they ever filed. Collapse to one (most-recent) hit per
    # vendor — rows are already ordered created_at desc — and re-apply
    # the caller's ``limit`` to the deduplicated set.
    if qtype == "name":
        seen: set[str] = set()
        deduped: list[SearchHit] = []
        for hit in hits:
            if hit.vendor_id in seen:
                continue
            seen.add(hit.vendor_id)
            deduped.append(hit)
            if len(deduped) >= limit:
                break
        return deduped

    return hits
