"""Tests for the WhatsApp dispatch stack.

Coverage targets the parts that don't need a live network:
  * phone normalizer edge cases
  * template payload shape + variable ordering
  * delivery short-circuits (disabled, no phone, dry-run)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services.whatsapp_delivery import (
    WhatsAppDeliveryResult,
    normalize_phone_e164,
    send_whatsapp_template,
    whatsapp_configured,
)
from app.services.whatsapp_templates import (
    DECISION_TEMPLATE,
    RENEWAL_TEMPLATE,
    build_renewal_threshold_components,
    build_reviewer_decision_components,
)


# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Local 10-digit MX → prepend country code 52
        ("5512345678", "525512345678"),
        # Spaces and parens stripped, country code preserved
        ("+52 55 1234 5678", "525512345678"),
        ("(55) 1234-5678", "525512345678"),
        # Already-E.164 input survives intact
        ("525512345678", "525512345678"),
        # WhatsApp's quirky "521" prefix for MX mobiles (legacy)
        ("5215512345678", "5215512345678"),
        # US-style 11-digit number with leading 1
        ("12025550100", "12025550100"),
    ],
)
def test_normalize_valid_phones(raw, expected):
    assert normalize_phone_e164(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "abc", "123", "1"])
def test_normalize_rejects_too_short_or_empty(raw):
    assert normalize_phone_e164(raw) is None


# ---------------------------------------------------------------------------
# Template payloads
# ---------------------------------------------------------------------------


def test_renewal_components_match_meta_shape():
    components = build_renewal_threshold_components(
        vendor_name="Aurora Demo",
        requirement_name="Constancia REPSE",
        due_date=date(2026, 5, 30),
        days_remaining=7,
        severity="yellow",
    )
    assert isinstance(components, list)
    assert len(components) == 1
    body = components[0]
    assert body["type"] == "body"
    params = body["parameters"]
    # Variable ordering must match the submitted template:
    # {{1}} vendor, {{2}} requirement, {{3}} date, {{4}} severity hint
    assert [p["text"] for p in params] == [
        "Aurora Demo",
        "Constancia REPSE",
        "30/05/2026",
        "Próximo a vencer · faltan 7 d",
    ]


def test_renewal_components_handle_overdue():
    components = build_renewal_threshold_components(
        vendor_name="Aurora",
        requirement_name="CSF",
        due_date=date(2026, 5, 1),
        days_remaining=-14,
        severity="red",
    )
    # Sanity: the body parameter for overdue includes the d-vencido hint.
    hint = components[0]["parameters"][3]["text"]
    assert "Vencido" in hint
    assert "14" in hint


def test_decision_components_match_meta_shape():
    components = build_reviewer_decision_components(
        vendor_name="Aurora",
        requirement_name="Declaración IVA",
        decision_action="rejected",
        reviewer_name="Ada Reyes",
    )
    params = components[0]["parameters"]
    # {{1}} vendor, {{2}} requirement, {{3}} decision label, {{4}} reviewer
    assert [p["text"] for p in params] == [
        "Aurora",
        "Declaración IVA",
        "Rechazado",
        "Ada Reyes",
    ]


def test_decision_components_fallback_reviewer_name():
    components = build_reviewer_decision_components(
        vendor_name="Aurora",
        requirement_name="Declaración IVA",
        decision_action="approved",
        reviewer_name=None,
    )
    # No reviewer → default to "Legal Shelf" so the template still has a {{4}}
    assert components[0]["parameters"][3]["text"] == "Legal Shelf"


# ---------------------------------------------------------------------------
# send_whatsapp_template short-circuits
# ---------------------------------------------------------------------------


def test_send_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    result = send_whatsapp_template(
        to_phone="5215512345678",
        template_name=RENEWAL_TEMPLATE,
        components=[],
    )
    assert result.status == "skipped_disabled"
    assert result.delivered is False


def test_send_skips_when_credentials_missing(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    result = send_whatsapp_template(
        to_phone="5215512345678",
        template_name=RENEWAL_TEMPLATE,
        components=[],
    )
    assert result.status == "skipped_not_configured"


def test_send_skips_when_phone_unparsable(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "stub")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "stub")
    result = send_whatsapp_template(
        to_phone="abc",
        template_name=RENEWAL_TEMPLATE,
        components=[],
    )
    assert result.status == "skipped_no_recipient"


def test_send_dry_run_does_not_call_meta(monkeypatch, caplog):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_DRY_RUN", True)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "stub")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "stub")
    with patch(
        "app.services.whatsapp_delivery.urllib.request.urlopen"
    ) as mock_urlopen:
        result = send_whatsapp_template(
            to_phone="5215512345678",
            template_name=DECISION_TEMPLATE,
            components=build_reviewer_decision_components(
                vendor_name="Aurora",
                requirement_name="CSF",
                decision_action="approved",
                reviewer_name="Ada Reyes",
            ),
        )
    assert result.status == "skipped_dry_run"
    assert mock_urlopen.call_count == 0


def test_whatsapp_configured_reads_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    assert whatsapp_configured() is False
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "stub")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "stub")
    assert whatsapp_configured() is True


# Smoke sanity — type signature surface
def test_delivery_result_dataclass_is_frozen():
    r = WhatsAppDeliveryResult(delivered=True, status="sent", message_id="m1")
    with pytest.raises(Exception):
        r.delivered = False  # type: ignore[misc]
