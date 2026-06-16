"""Prompt registry — maps a requirement to its versioned prompt file.

Prompts live as Markdown files under ``prompts/`` and are loaded at
import time so a missing prompt fails fast at boot rather than mid-
upload. Each file's basename (e.g. ``csf_sat.v1``) is the
``prompt_version`` persisted on ``DocumentInspection.shadow_prompt_version``
so an offline diff can be replayed against the exact prompt that
produced the row.

Resolution order, given a requirement_code like ``REC-SAT-CSF-2026``:

1. Direct match on the canonical document slug
   (``opinion_32d_sat`` / ``csf_sat`` / ``repse_stps`` / ``imss_pago``)
   derived from ``_slug_for_requirement``.
2. Fall back to ``base`` — the generic extraction prompt — when the
   requirement is in the catalog but not in the supported initial
   scope.

Adding a new supported requirement is a two-step PR: drop a new
``<slug>.vN.md`` file in ``prompts/`` and add a mapping entry to
``_REQUIREMENT_SLUG_RULES``. No migration, no config change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Canonical slug → prompt-file stem (without ``.md``). Bump the version
# suffix when prompts change so the persisted ``shadow_prompt_version``
# disambiguates old rows from new ones.
#
# v2 (Phase C): every extraction prompt additionally instructs the model
# to inspect for fabrication signals and report them via the new
# ``authenticity_concerns`` / ``looks_fabricated`` /
# ``authenticity_confidence`` tool fields. The v1 files stay on disk so
# persisted ``shadow_prompt_version`` values remain replayable.
#
# ``authenticity_deep`` is the escalation-tier prompt: a deeper,
# authenticity-focused pass run on the stronger model when the triage
# tier (or the deterministic verdict / requirement risk level) flags
# the document. It is requirement-agnostic — the requirement context
# still arrives via the user prompt.
# Per-tier slug → prompt-file stem.
#
# The TRIAGE tier (cheap Haiku per-upload pass) uses the v2 extraction
# prompts. The DEEP/comprehension tier (stronger model + adaptive
# thinking, Phase 1) uses the v3 prompts: they fold the v2 extraction +
# authenticity guidance together with the comprehension contract
# (``document_understanding``: purpose, key_facts, status_assessment,
# obligation_satisfaction, discrepancies). Both stems stay on disk so a
# persisted ``shadow_prompt_version`` is always replayable.
_TRIAGE_SLUG_TO_PROMPT: dict[str, str] = {
    "csf_sat": "csf_sat.v2",
    "opinion_32d_sat": "opinion_32d.v2",
    "repse_stps": "repse_stps.v2",
    "imss_pago": "imss_pago.v2",
    "base": "base.v2",
}
_DEEP_SLUG_TO_PROMPT: dict[str, str] = {
    "csf_sat": "csf_sat.v3",
    "opinion_32d_sat": "opinion_32d.v3",
    "repse_stps": "repse_stps.v3",
    "imss_pago": "imss_pago.v3",
    "base": "base.v3",
}

# Requirement slugs we explicitly support (excludes the generic ``base``
# fallback). Used by the Phase-2 scope listing.
_SUPPORTED_SLUGS = ["csf_sat", "opinion_32d_sat", "repse_stps", "imss_pago"]


@dataclass(frozen=True)
class PromptBundle:
    """Loaded prompt + its version stamp."""

    slug: str
    version: str  # file stem, e.g. "csf_sat.v1"
    system_prompt: str  # full prompt body (cached at module load)


def _load_prompt(stem: str) -> str:
    path = _PROMPTS_DIR / f"{stem}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Document-analysis prompt {stem!r} not found at {path}. "
            "Every entry in _SLUG_TO_PROMPT must have a matching file."
        )
    return path.read_text(encoding="utf-8")


def _load_bundle(slug: str, stem: str) -> PromptBundle:
    return PromptBundle(slug=slug, version=stem, system_prompt=_load_prompt(stem))


# Eagerly load every prompt at import time so a missing/typo'd prompt
# file is a boot-time failure (loud) rather than a per-upload failure
# (silent until the affected requirement is uploaded).
_TRIAGE_PROMPTS: dict[str, PromptBundle] = {
    slug: _load_bundle(slug, stem) for slug, stem in _TRIAGE_SLUG_TO_PROMPT.items()
}
_DEEP_PROMPTS: dict[str, PromptBundle] = {
    slug: _load_bundle(slug, stem) for slug, stem in _DEEP_SLUG_TO_PROMPT.items()
}
_ESCALATION_PROMPT: PromptBundle = _load_bundle(
    "authenticity_deep", "authenticity_deep.v1"
)


# Requirement-code substring rules. The portal sends a
# ``requirement_code`` like ``REC-SAT-CSF-2026`` or
# ``REC-IMSS-PAGO-2026-M04``; we match on lowercase substrings so a
# small set of rules covers the catalog without enumerating every
# (institution, period) combination.
#
# Order matters: more specific rules first. "imss-pago" must match
# before "imss" alone would (if we ever add an IMSS-generic fallback).
_REQUIREMENT_SLUG_RULES: list[tuple[str, str]] = [
    ("opinion-cumplimiento-32d", "opinion_32d_sat"),
    ("opinion-32d", "opinion_32d_sat"),
    ("opinion-cumplimiento", "opinion_32d_sat"),
    ("constancia-situacion-fiscal", "csf_sat"),
    ("csf", "csf_sat"),
    ("constancia-repse", "repse_stps"),
    ("registro-repse", "repse_stps"),
    ("repse", "repse_stps"),
    ("imss-comprobante-pago", "imss_pago"),
    ("imss-pago", "imss_pago"),
    ("imss-ema", "imss_pago"),
    ("comprobante-pago-imss", "imss_pago"),
]


def _slug_for_requirement(
    requirement_code: str | None,
    requirement_name: str,
) -> str:
    """Pick the most specific supported slug for this requirement.

    Returns ``"base"`` when the requirement is outside the Phase-2
    initial scope (CSF, Opinión 32-D, REPSE, IMSS pago). The base
    prompt still produces a valid extraction; it just doesn't include
    document-type-specific guidance.
    """
    haystack = f"{requirement_code or ''} {requirement_name}".lower().replace("_", "-")
    for needle, slug in _REQUIREMENT_SLUG_RULES:
        if needle in haystack:
            return slug
    return "base"


def get_prompt_for_requirement(
    *,
    requirement_code: str | None,
    requirement_name: str,
) -> PromptBundle:
    """Return the TRIAGE-tier (v2) extraction prompt for a requirement.

    Always succeeds — falls back to ``base`` when no specific match is
    found. The result includes ``version`` (the file stem) which the
    provider persists to ``shadow_prompt_version``.
    """
    slug = _slug_for_requirement(requirement_code, requirement_name)
    return _TRIAGE_PROMPTS[slug]


def get_comprehension_prompt_for_requirement(
    *,
    requirement_code: str | None,
    requirement_name: str,
) -> PromptBundle:
    """Return the DEEP-tier (v3) comprehension prompt for a requirement.

    Phase 1 — the deep/escalation tier is requirement-aware: deep
    *understanding* (what the document proves, whether it satisfies the
    obligation) is inherently type-specific, so the deeper pass uses the
    per-type v3 prompt rather than the requirement-agnostic
    ``authenticity_deep`` prompt. Falls back to ``base`` (v3) outside the
    supported scope.
    """
    slug = _slug_for_requirement(requirement_code, requirement_name)
    return _DEEP_PROMPTS[slug]


def get_escalation_prompt() -> PromptBundle:
    """Return the legacy requirement-agnostic deep authenticity prompt.

    Retained for replay/back-compat. Phase 1 routes the deep tier
    through ``get_comprehension_prompt_for_requirement`` instead, which
    folds the same authenticity guidance into per-type v3 prompts.
    """
    return _ESCALATION_PROMPT


def all_supported_slugs() -> list[str]:
    """Return every requirement slug we explicitly support.

    Used by the docs/Phase-2 report to enumerate the initial scope
    without re-hardcoding it.
    """
    return list(_SUPPORTED_SLUGS)
