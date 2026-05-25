"""Provider-portal UX pass (2026-05-25) — upload-URL builders.

The frontend intake wizard at ``/portal/upload`` falls back to
hardcoded defaults (``institution_code="sat"``, ``load_type="mensual"``,
``requirement_name=requirements[5]``) whenever a URL param is missing.
That fallback used to surface as plausible-but-wrong context when the
provider opened the wizard from the calendar.

The 2026-05-25 UX pass closes the gap by threading the full triad
(``requirement`` name, ``institution``, ``load_type``) into all three
upload-URL builders alongside the canonical
``(requirement_code, period_key)`` pair. These tests pin that contract.
"""

from __future__ import annotations

from app.api.v1.portal import (
    _calendar_reupload_href,
    _calendar_upload_href,
    _onboarding_reupload_href,
)
from app.services.evidence_slots import SlotKey, SlotView


def _params(url: str) -> dict[str, str]:
    assert url.startswith("/portal/upload?"), url
    from urllib.parse import parse_qsl

    return dict(parse_qsl(url.split("?", 1)[1], keep_blank_values=True))


def test_calendar_upload_href_emits_full_context() -> None:
    """The main calendar grid builder must surface every field the
    wizard needs so Step 1 renders without the hardcoded fallbacks."""
    url = _calendar_upload_href(
        year=2026,
        code="REC-IMSS-2026-01",
        period_key="2026-01",
        name="Pago bimestral IMSS",
        institution="imss",
        load_type="bimestral",
    )
    qp = _params(url)
    assert qp["requirement_code"] == "REC-IMSS-2026-01"
    assert qp["period_key"] == "2026-01"
    assert qp["period_label"] == "2026-01"
    assert qp["requirement"] == "Pago bimestral IMSS"
    assert qp["institution"] == "imss"
    assert qp["load_type"] == "bimestral"
    assert "v2" not in qp


def test_calendar_upload_href_appends_v2_flag() -> None:
    url = _calendar_upload_href(
        year=2026,
        code="REC-IMSS-2026-01",
        period_key="2026-01",
        name="Pago bimestral IMSS",
        institution="imss",
        load_type="bimestral",
        v2_mode=True,
    )
    assert _params(url)["v2"] == "1"


def test_calendar_upload_href_back_compat_without_optional_fields() -> None:
    """Older callers that don't pass the new optional fields must still
    receive a valid URL — the wizard then falls back to its empty-
    field rendering rather than the old hardcoded defaults."""
    url = _calendar_upload_href(
        year=2026, code="REC-SAT-2026-04-anual", period_key="2026-04"
    )
    qp = _params(url)
    assert qp["requirement_code"] == "REC-SAT-2026-04-anual"
    assert qp["period_key"] == "2026-04"
    assert "requirement" not in qp
    assert "institution" not in qp
    assert "load_type" not in qp


def _make_view(
    *,
    requirement_code: str | None,
    requirement_name: str | None,
    institution: str | None,
    load_type: str | None,
    period_key: str | None,
    state: str = "missing",
    current_submission_id: str | None = None,
) -> SlotView:
    return SlotView(
        slot_key=SlotKey(
            workspace_id="ws-1",
            client_id="cl-1",
            vendor_id="v-1",
            requirement_code=requirement_code,
            period_key=period_key,
        ),
        state=state,  # type: ignore[arg-type]
        requirement_code=requirement_code,
        period_key=period_key,
        requirement_name=requirement_name,
        institution=institution,
        load_type=load_type,
        required=True,
        current_submission_id=current_submission_id,
        current_status=None,
        submitted_at_iso=None,
        superseded_count=0,
    )


def test_onboarding_reupload_href_emits_institution_and_name() -> None:
    """Onboarding slots are non-periodic, so ``period_key`` /
    ``load_type`` are absent on purpose. ``institution`` + name must
    still surface."""
    view = _make_view(
        requirement_code="ONB-IMSS-AlTA",
        requirement_name="Alta patronal IMSS",
        institution="imss",
        load_type=None,
        period_key=None,
    )
    qp = _params(_onboarding_reupload_href(view))
    assert qp["requirement_code"] == "ONB-IMSS-AlTA"
    assert qp["requirement"] == "Alta patronal IMSS"
    assert qp["institution"] == "imss"
    assert qp["from"] == "onboarding"


def test_calendar_reupload_href_emits_full_context() -> None:
    """The dashboard suggested-action builder must match the calendar
    builder's coverage so reupload CTAs hand off the same context."""
    view = _make_view(
        requirement_code="REC-IMSS-2026-01",
        requirement_name="Pago bimestral IMSS",
        institution="imss",
        load_type="bimestral",
        period_key="2026-01",
        state="rejected",
        current_submission_id="sub-1",
    )
    qp = _params(_calendar_reupload_href(view))
    assert qp["requirement_code"] == "REC-IMSS-2026-01"
    assert qp["requirement"] == "Pago bimestral IMSS"
    assert qp["institution"] == "imss"
    assert qp["load_type"] == "bimestral"
    assert qp["period_key"] == "2026-01"
    assert qp["period_label"] == "2026-01"
    assert qp["replaces"] == "sub-1"
