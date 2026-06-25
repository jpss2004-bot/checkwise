"""CW-LOG-001 — delivery logs/errors must not retain full phone numbers,
message bodies, or raw provider response bodies."""

from __future__ import annotations

import io
import logging
import urllib.error
from unittest.mock import patch

import pytest

from app.services import messaging_delivery, whatsapp_delivery


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("525511112222", "****2222"),
        ("+52 55 1234 5678", "****5678"),
        ("", "****"),
        (None, "****"),
        ("12", "****"),
    ],
)
def test_mask_phone(raw, expected) -> None:
    assert messaging_delivery._mask_phone(raw) == expected  # noqa: SLF001
    assert whatsapp_delivery._mask_phone(raw) == expected  # noqa: SLF001


def test_sms_dry_run_logs_masked_phone_and_no_body(
    caplog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(messaging_delivery.settings, "MESSAGING_ENABLED", True)
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_ENABLED", False)
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_DRY_RUN", True)
    with caplog.at_level(logging.INFO, logger="checkwise.messaging_delivery"):
        messaging_delivery.send_message(
            to_phone="525511112222", body="texto secreto del mensaje"
        )
    assert "525511112222" not in caplog.text
    assert "texto secreto" not in caplog.text
    assert "****2222" in caplog.text
    assert "body_len=" in caplog.text


def test_twilio_http_error_drops_phone_and_provider_body(
    caplog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(messaging_delivery.settings, "MESSAGING_ENABLED", True)
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_ENABLED", True)
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_DRY_RUN", False)
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_FROM_NUMBER", "+15005550006")

    def _raise(req, *, timeout):  # noqa: ARG001
        raise urllib.error.HTTPError(
            req.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"message":"secret provider detail","code":21211}'),
        )

    with caplog.at_level(logging.WARNING, logger="checkwise.messaging_delivery"), patch(
        "app.services.messaging_delivery.urllib.request.urlopen", _raise
    ):
        r = messaging_delivery.send_message(to_phone="525511112222", body="x")

    assert r.error == "http_401"  # no raw provider body
    assert "secret provider detail" not in caplog.text
    assert "525511112222" not in caplog.text
    assert "****2222" in caplog.text


def test_twilio_network_error_masks_phone(
    caplog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(messaging_delivery.settings, "MESSAGING_ENABLED", True)
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_ENABLED", True)
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_DRY_RUN", False)
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(messaging_delivery.settings, "TWILIO_FROM_NUMBER", "+15005550006")

    def _raise(req, *, timeout):  # noqa: ARG001
        raise urllib.error.URLError("connection refused")

    with caplog.at_level(logging.WARNING, logger="checkwise.messaging_delivery"), patch(
        "app.services.messaging_delivery.urllib.request.urlopen", _raise
    ):
        r = messaging_delivery.send_message(to_phone="525511112222", body="x")

    assert r.error == "network: connection refused"
    assert "525511112222" not in caplog.text
    assert "****2222" in caplog.text


def test_whatsapp_http_error_drops_provider_body(
    caplog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whatsapp_delivery.settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(whatsapp_delivery.settings, "WHATSAPP_DRY_RUN", False)
    monkeypatch.setattr(whatsapp_delivery.settings, "WHATSAPP_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(whatsapp_delivery.settings, "WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(whatsapp_delivery.settings, "WHATSAPP_API_VERSION", "v19.0")

    def _raise(req, *, timeout):  # noqa: ARG001
        raise urllib.error.HTTPError(
            req.full_url,
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"error":{"message":"template not approved"}}'),
        )

    with caplog.at_level(logging.WARNING, logger="checkwise.whatsapp_delivery"), patch(
        "app.services.whatsapp_delivery.urllib.request.urlopen", _raise
    ):
        r = whatsapp_delivery.send_whatsapp_template(
            to_phone="525511112222",
            template_name="generic_template",
            components=[{"type": "body", "parameters": [{"type": "text", "text": "Aurora"}]}],
        )

    assert r.error == "http_400"
    assert "template not approved" not in caplog.text
