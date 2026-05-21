from __future__ import annotations

from app.core.config import settings
from app.services.email_delivery import smtp_configured


def test_smtp_configured_accepts_primary_env_names(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")

    monkeypatch.setattr(settings, "EMAIL_SMTP_HOST", "")
    monkeypatch.setattr(settings, "EMAIL_SMTP_USER", "")
    monkeypatch.setattr(settings, "EMAIL_SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "EMAIL_FROM", "")

    assert smtp_configured()


def test_smtp_configured_accepts_legacy_email_env_names(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "")

    monkeypatch.setattr(settings, "EMAIL_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "EMAIL_SMTP_USER", "sender@example.com")
    monkeypatch.setattr(settings, "EMAIL_SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(settings, "EMAIL_FROM", "sender@example.com")

    assert smtp_configured()


def test_smtp_configured_false_without_password(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")

    monkeypatch.setattr(settings, "EMAIL_SMTP_HOST", "")
    monkeypatch.setattr(settings, "EMAIL_SMTP_USER", "")
    monkeypatch.setattr(settings, "EMAIL_SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "EMAIL_FROM", "")

    assert not smtp_configured()
