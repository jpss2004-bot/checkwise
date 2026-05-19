#!/usr/bin/env python3
"""Record a professional CheckWise demo video.

Drives a headless Chromium at 1920×1080 through the 7-step demo
path from docs/SYSTEM_UX_AUDIT_REPORT.pdf. Adds:

  - branded intro + outro cards (data: URLs)
  - injected animated cursor (teal, soft shadow)
  - click ripple effect
  - bottom caption bar (dark background, backdrop blur)
  - smooth interpolated mouse motion between clicks
  - typing animation on form fields

Captures a single continuous WebM (Playwright native), then post-
processes to MP4 H.264 1080p via ffmpeg.

Output:
  docs/audit-screenshots/2026-05-18-system-audit/demo.mp4

Prereqs (one-time):
  - ./dev_demo.sh — boots Docker + Postgres + seed + uvicorn + Next
  - backend/.venv has playwright + chromium installed (see P1.9 work)
  - ffmpeg installed (brew install ffmpeg)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "audit-screenshots" / "2026-05-18-system-audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR = OUT_DIR / "_raw_demo"
RAW_DIR.mkdir(exist_ok=True)
OUT_MP4 = OUT_DIR / "demo.mp4"

API = "http://127.0.0.1:8000"
APP = "http://localhost:3000"

VIEWPORT = {"width": 1920, "height": 1080}
VIDEO_SIZE = {"width": 1920, "height": 1080}

ACCOUNTS = {
    "provider": ("boss.demo@checkwise.mx", "BossDemo!2026"),
    "client": ("cliente.demo@checkwise.mx", "ClienteDemo!2026"),
    "admin": ("ada@legalshelf.mx", "demo1234"),
}


# ── Injected cursor + caption + ripple ────────────────────────────

INJECT_JS = r"""
(() => {
  // Re-install on every navigation: window flags survive but the DOM
  // elements get torn down with the previous document, so we check for
  // the actual element rather than a window flag.
  if (document.getElementById('__demo_cursor')) return;

  const ROOT = document.documentElement;

  // Cursor
  const cursor = document.createElement('div');
  cursor.id = '__demo_cursor';
  Object.assign(cursor.style, {
    position: 'fixed',
    width: '24px',
    height: '24px',
    background: 'rgba(13, 132, 117, 0.85)',
    border: '3px solid white',
    borderRadius: '50%',
    pointerEvents: 'none',
    zIndex: '2147483647',
    transform: 'translate(-50%, -50%)',
    boxShadow: '0 4px 14px rgba(0,0,0,0.35)',
    transition: 'transform 0.08s ease-out',
    opacity: '0',
  });
  ROOT.appendChild(cursor);

  let cursorX = window.innerWidth / 2;
  let cursorY = window.innerHeight / 2;
  function moveCursor(x, y) {
    cursorX = x; cursorY = y;
    cursor.style.left = x + 'px';
    cursor.style.top = y + 'px';
    cursor.style.opacity = '1';
  }
  window.addEventListener('mousemove', e => moveCursor(e.clientX, e.clientY));

  // Click ripple on real mousedown
  window.addEventListener('mousedown', e => {
    const ripple = document.createElement('div');
    Object.assign(ripple.style, {
      position: 'fixed',
      left: e.clientX + 'px',
      top: e.clientY + 'px',
      width: '12px',
      height: '12px',
      background: 'rgba(13, 132, 117, 0.45)',
      border: '2px solid rgba(13, 132, 117, 0.9)',
      borderRadius: '50%',
      pointerEvents: 'none',
      zIndex: '2147483646',
      transform: 'translate(-50%, -50%) scale(1)',
      transition: 'all 0.55s cubic-bezier(.2,.7,.3,1)',
      opacity: '1',
    });
    ROOT.appendChild(ripple);
    requestAnimationFrame(() => {
      ripple.style.transform = 'translate(-50%, -50%) scale(5)';
      ripple.style.opacity = '0';
    });
    setTimeout(() => ripple.remove(), 700);
    cursor.style.transform = 'translate(-50%, -50%) scale(0.85)';
    setTimeout(() => { cursor.style.transform = 'translate(-50%, -50%) scale(1)'; }, 140);
  }, true);

  // Caption bar
  const cap = document.createElement('div');
  cap.id = '__demo_caption';
  Object.assign(cap.style, {
    position: 'fixed',
    bottom: '48px',
    left: '50%',
    transform: 'translateX(-50%) translateY(20px)',
    background: 'rgba(15, 23, 42, 0.94)',
    color: '#ffffff',
    padding: '14px 28px',
    borderRadius: '10px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif',
    fontSize: '20px',
    fontWeight: '500',
    lineHeight: '1.4',
    letterSpacing: '0.01em',
    maxWidth: '76%',
    textAlign: 'center',
    zIndex: '2147483645',
    boxShadow: '0 8px 28px rgba(0,0,0,0.4)',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    opacity: '0',
    transition: 'opacity 0.28s ease, transform 0.28s ease',
    pointerEvents: 'none',
  });
  ROOT.appendChild(cap);

  // Subtle teal eyebrow above caption text
  const eyebrow = document.createElement('div');
  eyebrow.id = '__demo_caption_eyebrow';
  Object.assign(eyebrow.style, {
    fontSize: '11px',
    fontWeight: '700',
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    color: '#5eead4',
    marginBottom: '6px',
    opacity: '0.95',
  });
  cap.appendChild(eyebrow);

  const bodyEl = document.createElement('div');
  bodyEl.id = '__demo_caption_body';
  cap.appendChild(bodyEl);

  window.__caption = (text, eyebrowText) => {
    eyebrow.textContent = eyebrowText || 'CHECKWISE · DEMO';
    bodyEl.textContent = text;
    cap.style.opacity = '1';
    cap.style.transform = 'translateX(-50%) translateY(0)';
  };
  window.__caption_clear = () => {
    cap.style.opacity = '0';
    cap.style.transform = 'translateX(-50%) translateY(20px)';
  };
})();
"""


# ── Branded intro / outro cards (data URLs) ───────────────────────

def card_html(eyebrow: str, title: str, subtitle: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>CheckWise</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ height: 100%; font-family: 'Inter', -apple-system, sans-serif; background: #ffffff; }}
.wrap {{ display: flex; align-items: center; justify-content: center; height: 100vh; padding: 80px; }}
.card {{ max-width: 1100px; width: 100%; }}
.brand-bar {{ position: fixed; top: 0; left: 0; right: 0; height: 14px; background: #0d8475; }}
.brand-mark {{ position: fixed; top: 24px; left: 64px; color: #0d8475; font-weight: 700; letter-spacing: 0.12em; font-size: 14px; }}
.eyebrow {{ color: #0d8475; font-size: 16px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 24px; }}
.title {{ color: #0f172a; font-size: 96px; font-weight: 700; letter-spacing: -0.025em; line-height: 1; margin-bottom: 28px; }}
.subtitle {{ color: #475569; font-size: 26px; font-weight: 400; line-height: 1.45; max-width: 820px; }}
.footer {{ position: fixed; bottom: 36px; left: 64px; right: 64px; display: flex; justify-content: space-between; color: #94a3b8; font-size: 13px; }}
.left-accent {{ position: fixed; top: 0; bottom: 0; left: 0; width: 10px; background: #0d8475; }}
</style></head><body>
<div class="brand-bar"></div>
<div class="left-accent"></div>
<div class="brand-mark">CHECKWISE · LEGAL SHELF</div>
<div class="wrap"><div class="card">
  <div class="eyebrow">{eyebrow}</div>
  <div class="title">{title}</div>
  <div class="subtitle">{subtitle}</div>
</div></div>
<div class="footer">
  <div>Plataforma de cumplimiento REPSE · México</div>
  <div>2026 · checkwise.mx</div>
</div>
</body></html>"""


INTRO_URL = "data:text/html;base64," + __import__("base64").b64encode(
    card_html(
        "DEMO · 2026-05-18",
        "CheckWise",
        "Cumplimiento documental REPSE guiado, trazable y accionable. Tres roles, una plataforma.",
    ).encode()
).decode()

OUTRO_URL = "data:text/html;base64," + __import__("base64").b64encode(
    card_html(
        "GRACIAS",
        "checkwise.mx",
        "Reporte ejecutivo, expediente trazable, revisión humana obligatoria. Listo para tu próxima demo a cliente.",
    ).encode()
).decode()


# ── Helpers ───────────────────────────────────────────────────────

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


def list_reports(token: str) -> list[dict]:
    req = urllib.request.Request(
        f"{API}/api/v1/reports/", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode()).get("items", [])


def list_vendors(token: str) -> list[dict]:
    req = urllib.request.Request(
        f"{API}/api/v1/client/vendors", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    return data.get("items") or data.get("vendors") or []


def reviewer_queue(token: str) -> list[dict]:
    req = urllib.request.Request(
        f"{API}/api/v1/reviewer/queue?limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode()).get("items", [])


def caption(page: Page, text: str, eyebrow: str | None = None) -> None:
    page.evaluate(
        "([t, e]) => window.__caption && window.__caption(t, e)",
        [text, eyebrow or "CHECKWISE · DEMO"],
    )


def caption_clear(page: Page) -> None:
    page.evaluate("() => window.__caption_clear && window.__caption_clear()")


def hover_smooth(page: Page, x: float, y: float, steps: int = 30) -> None:
    page.mouse.move(x, y, steps=steps)


def hover_element(page: Page, selector: str, steps: int = 30) -> tuple[float, float] | None:
    el = page.query_selector(selector)
    if not el:
        return None
    box = el.bounding_box()
    if not box:
        return None
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    hover_smooth(page, cx, cy, steps=steps)
    return cx, cy


def click_element(page: Page, selector: str, steps: int = 30) -> None:
    coords = hover_element(page, selector, steps=steps)
    if coords:
        page.mouse.down()
        time.sleep(0.05)
        page.mouse.up()
    else:
        page.click(selector)


def type_into(page: Page, selector: str, text: str, delay_ms: int = 75) -> None:
    hover_element(page, selector, steps=20)
    page.focus(selector)
    time.sleep(0.2)
    page.fill(selector, "")
    page.type(selector, text, delay=delay_ms)


def settle(page: Page, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        page.wait_for_timeout(80)


def goto(page: Page, url: str, *, wait_until: str = "networkidle") -> None:
    try:
        page.goto(url, wait_until=wait_until, timeout=30000)
    except Exception:
        pass
    # Re-inject after navigation (init script handles new docs, but defensively)
    try:
        page.evaluate(INJECT_JS)
    except Exception:
        pass


def inject_session(page: Page, login_response: dict) -> None:
    session = {
        "access_token": login_response["access_token"],
        "expires_at": login_response["expires_at"],
        "user": login_response["user"],
        "roles": login_response["roles"],
        "organization_ids": login_response.get("organization_ids", []),
    }
    page.evaluate(
        "(s) => window.localStorage.setItem('checkwise.admin.session.v1', JSON.stringify(s))",
        session,
    )


# ── Scenes ────────────────────────────────────────────────────────

def scene_intro(page: Page) -> None:
    goto(page, INTRO_URL)
    settle(page, 3.2)


def scene_landing(page: Page) -> None:
    goto(page, f"{APP}/")
    caption(page, "Página pública: propuesta REPSE en 5 segundos.", "ESCENA 1 · MARKETING")
    settle(page, 3.5)
    caption_clear(page)


def scene_provider(page: Page) -> None:
    # Login
    goto(page, f"{APP}/login")
    caption(page, "Iniciando sesión como proveedor.", "ESCENA 2 · PROVEEDOR")
    settle(page, 1.5)
    type_into(page, "#login-email", "boss.demo@checkwise.mx", delay_ms=55)
    type_into(page, "#login-password", "BossDemo!2026", delay_ms=55)
    settle(page, 0.5)
    click_element(page, "button[type='submit']")
    page.wait_for_url("**/portal/entra-a-tu-espacio", timeout=15000)
    settle(page, 1.0)

    # Workspace entry — confirm contact data
    caption(page, "Onramp humano: confirma datos antes de entrar.", "ESCENA 2 · PROVEEDOR")
    settle(page, 1.5)
    # Use page.fill (instant + React-compatible) for the transition form; the
    # viewer's eye is on the caption, not on per-key animation here.
    page.fill("#ws-first-name", "Marina")
    page.fill("#ws-last-name", "Quintero")
    settle(page, 0.8)
    # Hover then click — gives us the cursor visual + the click ripple.
    hover_element(page, "form button[type='submit']")
    settle(page, 0.4)
    page.locator("form button[type='submit']").click()
    try:
        page.wait_for_url("**/portal/dashboard", timeout=20000)
    except Exception:
        # Fallback: navigate directly if the entry form didn't redirect.
        goto(page, f"{APP}/portal/dashboard")
    settle(page, 1.2)

    # Dashboard
    caption(page, "Dashboard centrado en 'Tu siguiente acción'.", "ESCENA 2 · PROVEEDOR")
    settle(page, 3.0)
    page.mouse.wheel(0, 200)
    settle(page, 2.5)

    # Reports — Compliance Pulse
    goto(page, f"{APP}/portal/reports")
    caption(page, "Compliance Pulse: estado en 4 KPIs.", "ESCENA 2 · PROVEEDOR")
    settle(page, 3.5)

    # Open the first vendor_facing report
    token = login(*ACCOUNTS["provider"])["access_token"]
    reports = list_reports(token)
    target = next((r for r in reports if r.get("audience") == "vendor_facing"), reports[0] if reports else None)
    if target:
        goto(page, f"{APP}/portal/reports/{target['id']}")
        caption(page, "Editor de reporte con toolbar PDF (P1.8).", "ESCENA 2 · PROVEEDOR")
        settle(page, 3.0)

        # Hover + click Vista previa PDF
        try:
            hover_element(page, "a:has-text('Vista previa PDF')")
            settle(page, 0.8)
        except Exception:
            pass

        goto(page, f"{APP}/portal/reports/{target['id']}/print")
        caption(page, "Vista imprimible con sello 'Datos al…'.", "ESCENA 2 · PROVEEDOR")
        settle(page, 4.0)


def scene_client(page: Page) -> None:
    # Logout (clear localStorage) → login
    page.evaluate("() => window.localStorage.clear()")
    goto(page, f"{APP}/login")
    caption(page, "Ahora como cliente: vista del portafolio.", "ESCENA 3 · CLIENTE")
    settle(page, 1.5)
    type_into(page, "#login-email", "cliente.demo@checkwise.mx", delay_ms=55)
    type_into(page, "#login-password", "ClienteDemo!2026", delay_ms=55)
    settle(page, 0.4)
    click_element(page, "button[type='submit']")
    page.wait_for_url("**/client/dashboard", timeout=15000)
    settle(page, 1.2)

    caption(page, "Headline en una frase: 'Tienes 3 proveedores en amarillo.'", "ESCENA 3 · CLIENTE")
    settle(page, 4.0)

    # Vendors list
    goto(page, f"{APP}/client/vendors")
    caption(page, "Lista de proveedores con barra de riesgo.", "ESCENA 3 · CLIENTE")
    settle(page, 3.0)

    # Pick first vendor
    token = login(*ACCOUNTS["client"])["access_token"]
    vendors = list_vendors(token)
    if vendors:
        vid = vendors[0].get("id") or vendors[0].get("vendor_id")
        goto(page, f"{APP}/client/vendors/{vid}")
        caption(page, "Detalle del proveedor: narrativa de 6 secciones.", "ESCENA 3 · CLIENTE")
        settle(page, 4.5)


def scene_admin(page: Page) -> None:
    page.evaluate("() => window.localStorage.clear()")
    goto(page, f"{APP}/login")
    caption(page, "Como revisor interno de Legal Shelf.", "ESCENA 4 · REVISOR")
    settle(page, 1.5)
    type_into(page, "#login-email", "ada@legalshelf.mx", delay_ms=55)
    type_into(page, "#login-password", "demo1234", delay_ms=55)
    settle(page, 0.4)
    click_element(page, "button[type='submit']")
    page.wait_for_url("**/admin/reviewer", timeout=15000)
    settle(page, 1.2)

    caption(page, "Bandeja: ningún documento auto-aprueba.", "ESCENA 4 · REVISOR")
    settle(page, 3.5)

    token = login(*ACCOUNTS["admin"])["access_token"]
    queue = reviewer_queue(token)
    if queue:
        goto(page, f"{APP}/admin/reviewer/{queue[0]['submission_id']}")
        caption(page, "Detalle de revisión + decisión humana.", "ESCENA 4 · REVISOR")
        settle(page, 4.5)


def scene_outro(page: Page) -> None:
    goto(page, OUTRO_URL)
    settle(page, 3.5)


# ── Main ──────────────────────────────────────────────────────────

def run(pw: Playwright) -> Path:
    # Clean prior recording artifacts
    for f in RAW_DIR.glob("*.webm"):
        f.unlink()
    for f in RAW_DIR.glob("*.mp4"):
        f.unlink()

    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport=VIEWPORT,
        locale="es-MX",
        record_video_dir=str(RAW_DIR),
        record_video_size=VIDEO_SIZE,
    )
    # Re-inject the overlay JS on every navigation
    ctx.add_init_script(INJECT_JS)

    page = ctx.new_page()

    print("→ Intro card")
    scene_intro(page)
    print("→ Landing")
    scene_landing(page)
    print("→ Provider flow")
    scene_provider(page)
    print("→ Client flow")
    scene_client(page)
    print("→ Admin flow")
    scene_admin(page)
    print("→ Outro card")
    scene_outro(page)

    # Close context to flush video to disk
    ctx.close()
    browser.close()

    # Find the produced webm
    webms = sorted(RAW_DIR.glob("*.webm"))
    if not webms:
        raise SystemExit("no video produced")
    return webms[0]


def encode_mp4(webm: Path) -> Path:
    """Convert WebM (VP8) → MP4 H.264 1080p with sensible quality."""
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not on PATH; brew install ffmpeg")
    print(f"→ Encoding {webm.name} → MP4")
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(webm),
        "-vf", "scale=1920:1080:flags=lanczos",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(OUT_MP4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return OUT_MP4


if __name__ == "__main__":
    with sync_playwright() as pw:
        webm = run(pw)
    mp4 = encode_mp4(webm)
    # Probe duration + size for the user
    try:
        probe = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(mp4)],
            text=True,
        ).strip()
        dur = float(probe)
        size_mb = mp4.stat().st_size / (1024 * 1024)
        print(f"\n✓ {mp4.relative_to(ROOT)}  ({dur:.1f}s · {size_mb:.1f} MB)")
    except Exception:
        print(f"\n✓ {mp4.relative_to(ROOT)}")
