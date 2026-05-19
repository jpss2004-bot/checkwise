#!/usr/bin/env python3
"""Capture every page of the CheckWise stack as a PNG for the audit PDF.

Drives a headless Chromium via Playwright. Authenticates each of the
three demo roles (admin / provider / client) by POSTing to
/api/v1/auth/login and stashing the JWT into localStorage under the
same key the frontend uses (`checkwise.admin.session.v1`). Then
navigates each documented route, waits for content, and screenshots
the full visible viewport.

Requires: backend + frontend dev servers running at the default ports
(127.0.0.1:8000 and localhost:3000). Easiest path: `./dev_demo.sh`.

Outputs to `docs/audit-screenshots/2026-05-18-system-audit/`.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "audit-screenshots" / "2026-05-18-system-audit"
OUT.mkdir(parents=True, exist_ok=True)

API = "http://127.0.0.1:8000"
APP = "http://localhost:3000"
VIEWPORT = {"width": 1440, "height": 900}
DELAY = 0.6  # paint settle


@dataclass
class Shot:
    filename: str
    url: str
    role: str  # 'public' | 'admin' | 'provider' | 'client'
    label: str
    settle: float = DELAY


# ── Demo accounts (seeded by backend/scripts/dev_seed.py) ──
ACCOUNTS = {
    "admin": ("ada@legalshelf.mx", "demo1234"),
    "provider": ("boss.demo@checkwise.mx", "BossDemo!2026"),
    "client": ("cliente.demo@checkwise.mx", "ClienteDemo!2026"),
}


def login(email: str, password: str) -> dict:
    body = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def get_first_report_id(token: str, audience: str) -> str | None:
    req = urllib.request.Request(
        f"{API}/api/v1/reports/",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        items = json.loads(resp.read().decode()).get("items", [])
    for it in items:
        if it.get("audience") == audience:
            return it["id"]
    return items[0]["id"] if items else None


def get_first_vendor_id(token: str) -> str | None:
    req = urllib.request.Request(
        f"{API}/api/v1/client/vendors",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    items = data.get("items") or data.get("vendors") or []
    if items:
        return items[0].get("id") or items[0].get("vendor_id")
    return None


def get_first_submission_id(token: str) -> str | None:
    req = urllib.request.Request(
        f"{API}/api/v1/reviewer/queue?limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        items = json.loads(resp.read().decode()).get("items", [])
    return items[0]["submission_id"] if items else None


def inject_session(page: Page, login_response: dict) -> None:
    session = {
        "access_token": login_response["access_token"],
        "expires_at": login_response["expires_at"],
        "user": login_response["user"],
        "roles": login_response["roles"],
        "organization_ids": login_response.get("organization_ids", []),
    }
    page.add_init_script(
        f"window.localStorage.setItem('checkwise.admin.session.v1', "
        f"JSON.stringify({json.dumps(session)}));"
    )


def capture(page: Page, shot: Shot) -> None:
    out = OUT / shot.filename
    print(f"  → {shot.filename:40s}  {shot.url}")
    try:
        page.goto(shot.url, wait_until="networkidle", timeout=30000)
    except Exception as exc:
        print(f"    ! networkidle timed out ({exc.__class__.__name__}); continuing")
    time.sleep(shot.settle)
    page.screenshot(path=str(out), full_page=False)


def run(pw: Playwright) -> None:
    browser = pw.chromium.launch(headless=True)

    # ── Public shots (no auth) ──
    ctx_public = browser.new_context(viewport=VIEWPORT, locale="es-MX")
    page = ctx_public.new_page()
    for shot in [
        Shot("01-landing.png", f"{APP}/", "public", "Landing"),
        Shot("02-login.png", f"{APP}/login", "public", "Login"),
        Shot(
            "02b-login-error.png",
            f"{APP}/login",
            "public",
            "Login (wrong password)",
        ),
        Shot(
            "99-not-found.png",
            f"{APP}/this-truly-does-not-exist",
            "public",
            "404 page",
        ),
    ]:
        if shot.filename == "02b-login-error.png":
            # Special-case: fill bad creds then submit
            page.goto(shot.url, wait_until="networkidle")
            time.sleep(0.4)
            page.fill("#login-email", "ada@legalshelf.mx")
            page.fill("#login-password", "wrong-password")
            page.click('button[type="submit"]')
            time.sleep(1.0)
            page.screenshot(path=str(OUT / shot.filename), full_page=False)
            print(f"  → {shot.filename}")
        else:
            capture(page, shot)
    ctx_public.close()

    # ── Admin shots ──
    admin_login = login(*ACCOUNTS["admin"])
    token = admin_login["access_token"]
    submission_id = get_first_submission_id(token)
    admin_report_id = get_first_report_id(token, "internal_only")

    ctx_admin = browser.new_context(viewport=VIEWPORT, locale="es-MX")
    page = ctx_admin.new_page()
    inject_session(page, admin_login)

    admin_shots = [
        Shot("03-admin-reviewer-queue.png", f"{APP}/admin/reviewer", "admin", "Reviewer queue"),
        Shot("04-admin-dashboard.png", f"{APP}/admin/dashboard", "admin", "Admin dashboard"),
        Shot("05-admin-clients.png", f"{APP}/admin/clients", "admin", "Clients"),
        Shot("06-admin-vendors.png", f"{APP}/admin/vendors", "admin", "Vendors"),
        Shot("07-admin-requirements.png", f"{APP}/admin/requirements", "admin", "Requirements catalog"),
        Shot("09-admin-calendar.png", f"{APP}/admin/calendar", "admin", "Admin calendar"),
        Shot("10-admin-audit-log.png", f"{APP}/admin/audit-log", "admin", "Audit log"),
        Shot("11-admin-reports-list.png", f"{APP}/admin/reports", "admin", "Reports list"),
    ]
    if submission_id:
        admin_shots.insert(
            1,
            Shot(
                "08-admin-reviewer-detail.png",
                f"{APP}/admin/reviewer/{submission_id}",
                "admin",
                "Reviewer detail",
            ),
        )
    if admin_report_id:
        admin_shots.append(
            Shot(
                "12-admin-report-editor.png",
                f"{APP}/admin/reports/{admin_report_id}",
                "admin",
                "Report editor",
            )
        )
    for shot in admin_shots:
        capture(page, shot)
    ctx_admin.close()

    # ── Client shots ──
    client_login = login(*ACCOUNTS["client"])
    token = client_login["access_token"]
    vendor_id = get_first_vendor_id(token)
    client_report_id = get_first_report_id(token, "client_facing")

    ctx_client = browser.new_context(viewport=VIEWPORT, locale="es-MX")
    page = ctx_client.new_page()
    inject_session(page, client_login)
    client_shots = [
        Shot("13-client-dashboard.png", f"{APP}/client/dashboard", "client", "Client dashboard"),
        Shot("14-client-vendors.png", f"{APP}/client/vendors", "client", "Client vendors"),
        Shot("16-client-submissions.png", f"{APP}/client/submissions", "client", "Client submissions"),
        Shot("17-client-activity.png", f"{APP}/client/activity", "client", "Client activity"),
        Shot("18-client-calendar.png", f"{APP}/client/calendar", "client", "Client calendar"),
        Shot("19-client-reports.png", f"{APP}/client/reports", "client", "Client reports"),
    ]
    if vendor_id:
        client_shots.insert(
            2,
            Shot(
                "15-client-vendor-detail.png",
                f"{APP}/client/vendors/{vendor_id}",
                "client",
                "Vendor detail",
            ),
        )
    for shot in client_shots:
        capture(page, shot)
    if client_report_id:
        # Use the same session for the print page (which lives under /portal/*)
        capture(
            page,
            Shot(
                "26-portal-report-print.png",
                f"{APP}/portal/reports/{client_report_id}/print",
                "client",
                "Report print page",
                settle=1.5,
            ),
        )
    ctx_client.close()

    # ── Provider shots ──
    # Provider needs the entry-form contact confirmation before /portal/* is unlocked.
    provider_login = login(*ACCOUNTS["provider"])
    ctx_prov = browser.new_context(viewport=VIEWPORT, locale="es-MX")
    page = ctx_prov.new_page()
    inject_session(page, provider_login)

    # Step 1: workspace entry screen
    capture(page, Shot("20-portal-entry.png", f"{APP}/portal/entra-a-tu-espacio", "provider", "Portal entry"))

    # Step 2: confirm contact name + submit so subsequent routes are unlocked
    page.fill("input >> nth=0", "Marina")
    page.fill("input >> nth=1", "Quintero")
    try:
        page.click("button:has-text('Entrar a mi espacio')")
    except Exception:
        # Fallback if the label differs
        page.click("button[type='submit']")
    page.wait_for_url("**/portal/dashboard", timeout=15000)
    time.sleep(1.0)

    provider_shots = [
        Shot("21-portal-dashboard.png", f"{APP}/portal/dashboard", "provider", "Provider dashboard"),
        Shot("22-portal-onboarding.png", f"{APP}/portal/onboarding", "provider", "Onboarding"),
        Shot("23-portal-upload.png", f"{APP}/portal/upload", "provider", "Upload wizard"),
        Shot("24-portal-calendar.png", f"{APP}/portal/calendar", "provider", "Portal calendar"),
        Shot("25-portal-reports.png", f"{APP}/portal/reports", "provider", "Portal reports"),
    ]
    for shot in provider_shots:
        capture(page, shot)
    ctx_prov.close()

    browser.close()
    print(f"\n✓ All screenshots written to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    with sync_playwright() as pw:
        run(pw)
