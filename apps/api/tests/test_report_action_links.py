"""Client-routable action links in reports (CW-04).

The client monitors compliance and cannot upload, so report CTAs shown to a
CLIENT audience must deep-link into the client app (``/client/vendors/...``)
instead of the provider-only ``/portal/upload`` wizard. These are pure-function
unit tests (no DB) over the two seams that implement that rewrite.
"""

from __future__ import annotations

from app.services.dashboard_compute import client_vendor_focus_href
from app.services.reports.insights import _action_links_from_items


def test_client_vendor_focus_href_builds_client_deeplink() -> None:
    href = client_vendor_focus_href(
        "vendor-123", requirement_code="IMSS-SIPARE-001", period_key="2026-M03"
    )
    assert href == (
        "/client/vendors/vendor-123?focus=IMSS-SIPARE-001&period=2026-M03#documentos"
    )


def test_client_vendor_focus_href_without_params_anchors_to_card() -> None:
    assert client_vendor_focus_href("v1") == "/client/vendors/v1#documentos"


_ITEMS = [
    {
        "id": "a1",
        "type": "reupload",
        "priority": "high",
        "title": "Vuelve a cargar IMSS",
        "href": "/portal/upload?requirement_code=IMSS-SIPARE-001",
        "requirement_code": "IMSS-SIPARE-001",
        "period_key": "2026-M03",
    }
]


def test_action_links_default_keeps_provider_href() -> None:
    """No client_vendor_id → provider-facing behavior is untouched."""
    [link] = _action_links_from_items(_ITEMS)
    assert link["href"] == "/portal/upload?requirement_code=IMSS-SIPARE-001"
    assert link["title"] == "Vuelve a cargar IMSS"


def test_action_links_client_view_rewrites_to_client_deeplink() -> None:
    [link] = _action_links_from_items(_ITEMS, client_vendor_id="vendor-9")
    assert link["href"] == (
        "/client/vendors/vendor-9?focus=IMSS-SIPARE-001&period=2026-M03#documentos"
    )
    # Neutral CTA — the client views, it does not "vuelve a cargar".
    assert link["title"] == "Ver documento del proveedor"
    # Identity fields preserved for downstream rendering.
    assert link["requirement_code"] == "IMSS-SIPARE-001"
    assert link["period_key"] == "2026-M03"
