"""Verify the SecurityHeadersMiddleware contract.

The middleware is silent — no logs, no metrics — so the only way
to catch a regression (someone removes ``app.add_middleware`` or
re-orders middlewares in a way that swallows headers) is to assert
on the response shape.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_baseline_security_headers_present() -> None:
    """Every response must carry the non-HSTS baseline headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert (
        response.headers.get("Referrer-Policy")
        == "strict-origin-when-cross-origin"
    )
    assert "geolocation=()" in response.headers.get("Permissions-Policy", "")


def test_hsts_gated_on_environment() -> None:
    """HSTS must NOT be emitted in local — would lock localhost to HTTPS."""
    response = client.get("/health")
    if settings.is_local_env:
        assert "Strict-Transport-Security" not in response.headers
    else:
        hsts = response.headers.get("Strict-Transport-Security", "")
        assert "max-age=" in hsts
        assert "includeSubDomains" in hsts
