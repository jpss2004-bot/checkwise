"""Per-org daily cap for document-analysis provider calls.

Bounds worst-case spend on the Anthropic API during the Phase-2
shadow pilot. The cap is enforced as a sliding-window counter keyed by
``org_id`` on top of the existing rate-limit infrastructure (M4
Redis-backed sliding window), so the cap holds correctly across
workers when ``REDIS_URL`` is configured and degrades to per-process
counting otherwise.

The cap is intentionally **not** a hard SLA on the user. Tripping it
means: skip the Claude call for the rest of the 24-hour window for
this org, log a warning, persist ``shadow_error="daily_cap_exceeded"``
on the inspection row, and let the heuristic continue. The provider
never sees anything different — shadow mode means user-visible
behaviour does not change.

The window is 24 hours (86400 seconds), counted from the moment of
first call rather than wall-clock day boundaries. This is the right
semantics for a "no more than N per day" spend ceiling: a script
that fires 200 calls at 23:59 cannot fire 200 more at 00:01.

Setting ``DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG=0`` disables the cap
entirely (always allow). The orgless / dev path (``org_id=None``) is
counted against a single shared bucket so a misconfigured caller
can't bypass the cap by omitting the identifier.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.rate_limit import build_rate_limiter, hash_identifier

# A dedicated bucket so doc-analysis usage does not cross-deplete the
# existing ``ai_heavy_limiter`` (which protects the reports + Wise
# copilot endpoints, with looser per-minute / per-hour budgets).
_doc_analysis_daily_limiter = build_rate_limiter()

_WINDOW_SECONDS_DAY = 86400.0


def check_org_daily_quota(org_id: str | None) -> bool:
    """Return True when the call is within this org's daily quota.

    The check both reads and increments the counter atomically. A
    caller must invoke this exactly once per provider call attempt,
    BEFORE making the (paid) provider call. Returning ``False`` means
    the cap is reached and the caller MUST skip the provider call and
    record ``shadow_error="daily_cap_exceeded"``.

    Setting ``DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG=0`` disables the cap
    entirely (always returns True).
    """
    limit = settings.DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG
    if limit <= 0:
        return True
    # Hash the org id so an operator dumping the in-memory counter
    # state during debugging can't trivially derive the tenant list.
    bucket = f"docanalysis:org:{hash_identifier(org_id or '__none__')}"
    return _doc_analysis_daily_limiter.check(
        bucket, limit=limit, window_seconds=_WINDOW_SECONDS_DAY
    )


def reset_daily_quota() -> None:
    """Test hook. Drops every bucket in this limiter's namespace."""
    _doc_analysis_daily_limiter.reset()
