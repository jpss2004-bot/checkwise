#!/usr/bin/env python3
"""Record the narrated CheckWise demo video (v2 — paced to voice-over).

Drives a headless Chromium at 1920×1080 through the demo path. Reads
voice-over clip durations from
docs/audit-screenshots/2026-05-18-system-audit/voice/manifest.json
and times each scene's on-screen dwell to match the narration so
caption + voice + visuals stay in sync.

On-screen polish:
  - branded intro + outro cards (data: URLs)
  - injected animated cursor (teal, soft shadow)
  - click ripple on every interaction
  - bottom caption bar (eyebrow + body, glassmorphism)
  - element highlight system: draws a pulsing teal outline + label
    over any DOM element, used to point at UI features the narrator
    is explaining
  - smooth interpolated mouse motion
  - typing animation on credential fields

This script ONLY records a silent WebM. Audio mixing (voice +
music) happens in scripts/finalize_demo.py after recording so each
step is independently re-runnable.
"""
from __future__ import annotations

import base64
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
SILENT_MP4 = OUT_DIR / "demo.silent.mp4"
VOICE_MANIFEST = OUT_DIR / "voice" / "manifest.json"

API = "http://127.0.0.1:8000"
APP = "http://localhost:3000"

VIEWPORT = {"width": 1920, "height": 1080}
VIDEO_SIZE = {"width": 1920, "height": 1080}

# How much extra dwell time on screen AFTER the narration finishes.
# Gives the viewer a beat to absorb the UI before the next scene.
SCENE_TAIL = 0.6

ACCOUNTS = {
    "provider": ("boss.demo@checkwise.mx", "BossDemo!2026"),
    "client": ("cliente.demo@checkwise.mx", "ClienteDemo!2026"),
    "admin": ("ada@legalshelf.mx", "demo1234"),
}


# ── Voice-clip durations (drives scene pacing) ────────────────────

def load_durations() -> dict[str, float]:
    if not VOICE_MANIFEST.exists():
        raise SystemExit(
            f"Voice manifest not found at {VOICE_MANIFEST}. "
            "Run scripts/generate_voiceover.py first."
        )
    data = json.loads(VOICE_MANIFEST.read_text(encoding="utf-8"))
    return {k: float(v) for k, v in data["durations"].items()}


# ── Injected cursor + caption + highlight ─────────────────────────

INJECT_JS = r"""
(() => {
  // Re-install on every navigation — DOM elements get torn down with
  // the previous document, so we check for the actual element.
  if (document.getElementById('__demo_cursor')) return;

  const ROOT = document.documentElement;

  // Cursor — larger, with persistent ring + a faint trail for motion
  // legibility when the camera pans across the screen.
  const cursorTrail = document.createElement('div');
  cursorTrail.id = '__demo_cursor_trail';
  Object.assign(cursorTrail.style, {
    position: 'fixed',
    width: '48px', height: '48px',
    background: 'rgba(13, 132, 117, 0.18)',
    border: '2px solid rgba(13, 132, 117, 0.35)',
    borderRadius: '50%',
    pointerEvents: 'none',
    zIndex: '2147483646',
    transform: 'translate(-50%, -50%)',
    transition: 'left 0.18s ease-out, top 0.18s ease-out, opacity 0.2s ease',
    opacity: '0',
  });
  ROOT.appendChild(cursorTrail);

  const cursor = document.createElement('div');
  cursor.id = '__demo_cursor';
  Object.assign(cursor.style, {
    position: 'fixed',
    width: '28px', height: '28px',
    background: 'rgba(13, 132, 117, 0.95)',
    border: '4px solid white',
    borderRadius: '50%',
    pointerEvents: 'none',
    zIndex: '2147483647',
    transform: 'translate(-50%, -50%)',
    boxShadow: '0 6px 20px rgba(13, 132, 117, 0.5), 0 0 0 1px rgba(0,0,0,0.2)',
    transition: 'transform 0.08s ease-out',
    opacity: '0',
  });
  ROOT.appendChild(cursor);

  window.addEventListener('mousemove', e => {
    cursor.style.left = e.clientX + 'px';
    cursor.style.top = e.clientY + 'px';
    cursor.style.opacity = '1';
    cursorTrail.style.left = e.clientX + 'px';
    cursorTrail.style.top = e.clientY + 'px';
    cursorTrail.style.opacity = '1';
  });

  // Click ripple
  window.addEventListener('mousedown', e => {
    const ripple = document.createElement('div');
    Object.assign(ripple.style, {
      position: 'fixed',
      left: e.clientX + 'px', top: e.clientY + 'px',
      width: '12px', height: '12px',
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

  // Caption bar (bottom-center)
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
  const eyebrow = document.createElement('div');
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
  const body = document.createElement('div');
  cap.appendChild(body);

  window.__caption = (text, eyebrowText) => {
    eyebrow.textContent = eyebrowText || 'CHECKWISE · DEMO';
    body.textContent = text;
    cap.style.opacity = '1';
    cap.style.transform = 'translateX(-50%) translateY(0)';
  };
  window.__caption_clear = () => {
    cap.style.opacity = '0';
    cap.style.transform = 'translateX(-50%) translateY(20px)';
  };

  // ── Element highlight system ──
  // Draws a 4px teal outline + soft glow over a target element, plus
  // an optional label tooltip that points at the top-right corner.
  // The overlay is absolutely positioned, never disturbs the DOM,
  // and animates with a slow breathing pulse so it reads as
  // "look here" without distracting.
  let highlightObserver = null;

  window.__highlight = (selector, labelText) => {
    window.__unhighlight();
    const target = document.querySelector(selector);
    if (!target) return false;
    const box = document.createElement('div');
    box.id = '__demo_highlight';
    Object.assign(box.style, {
      position: 'fixed',
      pointerEvents: 'none',
      zIndex: '2147483640',
      border: '3px solid rgba(13, 132, 117, 0.95)',
      borderRadius: '10px',
      boxShadow: '0 0 0 6px rgba(13, 132, 117, 0.18), 0 0 30px rgba(13, 132, 117, 0.35)',
      transition: 'left 0.25s ease, top 0.25s ease, width 0.25s ease, height 0.25s ease, opacity 0.25s ease',
      opacity: '0',
      animation: 'demoBreathe 2.4s ease-in-out infinite',
    });

    // Inject keyframes once
    if (!document.getElementById('__demo_kf')) {
      const style = document.createElement('style');
      style.id = '__demo_kf';
      style.textContent = `@keyframes demoBreathe {
        0%, 100% { box-shadow: 0 0 0 6px rgba(13, 132, 117, 0.18), 0 0 30px rgba(13, 132, 117, 0.35); }
        50%      { box-shadow: 0 0 0 10px rgba(13, 132, 117, 0.10), 0 0 44px rgba(13, 132, 117, 0.55); }
      }`;
      document.head.appendChild(style);
    }

    ROOT.appendChild(box);

    // Optional label that sits above the highlight box, brand-colored
    let label = null;
    if (labelText) {
      label = document.createElement('div');
      label.id = '__demo_highlight_label';
      Object.assign(label.style, {
        position: 'fixed',
        pointerEvents: 'none',
        zIndex: '2147483641',
        background: 'rgba(13, 132, 117, 0.96)',
        color: 'white',
        padding: '8px 14px',
        borderRadius: '8px',
        fontFamily: '-apple-system, BlinkMacSystemFont, Inter, sans-serif',
        fontSize: '14px',
        fontWeight: '600',
        boxShadow: '0 6px 18px rgba(13, 132, 117, 0.35)',
        opacity: '0',
        transition: 'opacity 0.3s ease, transform 0.3s ease',
        transform: 'translateY(6px)',
        maxWidth: '420px',
        textAlign: 'center',
        lineHeight: '1.3',
      });
      label.textContent = labelText;
      ROOT.appendChild(label);
    }

    function place() {
      const r = target.getBoundingClientRect();
      const padX = 8, padY = 6;
      box.style.left = (r.left - padX) + 'px';
      box.style.top = (r.top - padY) + 'px';
      box.style.width = (r.width + padX * 2) + 'px';
      box.style.height = (r.height + padY * 2) + 'px';
      box.style.opacity = '1';
      if (label) {
        // Place label above the highlight if there's room, else below
        const labelGap = 12;
        label.style.opacity = '1';
        label.style.transform = 'translateY(0)';
        // Measure label after it's visible
        requestAnimationFrame(() => {
          const lr = label.getBoundingClientRect();
          let lx = r.left + (r.width / 2) - (lr.width / 2);
          lx = Math.max(16, Math.min(window.innerWidth - lr.width - 16, lx));
          let ly = r.top - lr.height - labelGap - padY;
          if (ly < 24) ly = r.bottom + padY + labelGap;
          label.style.left = lx + 'px';
          label.style.top = ly + 'px';
        });
      }
    }

    place();
    highlightObserver = setInterval(place, 100);
    return true;
  };

  window.__unhighlight = () => {
    if (highlightObserver) { clearInterval(highlightObserver); highlightObserver = null; }
    const b = document.getElementById('__demo_highlight');
    const l = document.getElementById('__demo_highlight_label');
    const s = document.getElementById('__demo_spotlight');
    if (b) b.remove();
    if (l) l.remove();
    if (s) s.remove();
  };

  // ── Spotlight mode ──
  // Dims the entire screen except a rectangular cutout over the target
  // element. Built from an SVG <mask>, so the cutout has a soft
  // feathered edge. The narrator can talk over it without the rest of
  // the screen competing for attention.
  let spotlightObserver = null;
  window.__spotlight = (selector, labelText) => {
    window.__unhighlight();
    const target = document.querySelector(selector);
    if (!target) return false;

    const layer = document.createElement('div');
    layer.id = '__demo_spotlight';
    Object.assign(layer.style, {
      position: 'fixed',
      inset: '0',
      pointerEvents: 'none',
      zIndex: '2147483639',
      opacity: '0',
      transition: 'opacity 0.3s ease',
    });
    layer.innerHTML = `
      <svg width="100%" height="100%" viewBox="0 0 ${window.innerWidth} ${window.innerHeight}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <mask id="__demo_mask">
            <rect width="100%" height="100%" fill="white"/>
            <rect id="__demo_cutout" x="0" y="0" width="0" height="0" rx="14" ry="14" fill="black"/>
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(7, 18, 35, 0.72)" mask="url(#__demo_mask)"/>
        <rect id="__demo_glow" x="0" y="0" width="0" height="0" rx="14" ry="14" fill="none" stroke="rgba(13, 132, 117, 0.95)" stroke-width="3"/>
      </svg>`;
    ROOT.appendChild(layer);

    let label = null;
    if (labelText) {
      label = document.createElement('div');
      label.id = '__demo_highlight_label';
      Object.assign(label.style, {
        position: 'fixed',
        pointerEvents: 'none',
        zIndex: '2147483641',
        background: 'rgba(13, 132, 117, 0.96)',
        color: 'white',
        padding: '10px 16px',
        borderRadius: '8px',
        fontFamily: '-apple-system, BlinkMacSystemFont, Inter, sans-serif',
        fontSize: '15px',
        fontWeight: '600',
        boxShadow: '0 8px 22px rgba(13, 132, 117, 0.45)',
        opacity: '0',
        transition: 'opacity 0.3s ease',
        maxWidth: '460px',
        textAlign: 'center',
        lineHeight: '1.3',
      });
      label.textContent = labelText;
      ROOT.appendChild(label);
    }

    function place() {
      const r = target.getBoundingClientRect();
      const pad = 10;
      const x = r.left - pad, y = r.top - pad;
      const w = r.width + pad * 2, h = r.height + pad * 2;
      const cutout = layer.querySelector('#__demo_cutout');
      const glow = layer.querySelector('#__demo_glow');
      if (cutout) {
        cutout.setAttribute('x', x); cutout.setAttribute('y', y);
        cutout.setAttribute('width', w); cutout.setAttribute('height', h);
      }
      if (glow) {
        glow.setAttribute('x', x); glow.setAttribute('y', y);
        glow.setAttribute('width', w); glow.setAttribute('height', h);
      }
      layer.style.opacity = '1';
      if (label) {
        label.style.opacity = '1';
        const lr = label.getBoundingClientRect();
        let lx = r.left + (r.width / 2) - (lr.width / 2);
        lx = Math.max(16, Math.min(window.innerWidth - lr.width - 16, lx));
        let ly = r.bottom + 22;
        if (ly + lr.height > window.innerHeight - 100) ly = r.top - lr.height - 22;
        label.style.left = lx + 'px';
        label.style.top = ly + 'px';
      }
    }
    place();
    spotlightObserver = setInterval(place, 120);
    return true;
  };

  // ── Fade-to-black transition ──
  // Returns a Promise so the recording script can await fade-in then
  // do the navigation, then await fade-out. Used between scenes to
  // smooth abrupt navigations into a deliberate cut.
  window.__fade = (toBlack, durationMs) => {
    let layer = document.getElementById('__demo_fade');
    if (!layer) {
      layer = document.createElement('div');
      layer.id = '__demo_fade';
      Object.assign(layer.style, {
        position: 'fixed',
        inset: '0',
        background: '#0f172a',
        pointerEvents: 'none',
        zIndex: '2147483644',
        opacity: '0',
        transition: `opacity ${durationMs}ms ease`,
      });
      ROOT.appendChild(layer);
    } else {
      layer.style.transition = `opacity ${durationMs}ms ease`;
    }
    return new Promise(res => {
      requestAnimationFrame(() => {
        layer.style.opacity = toBlack ? '1' : '0';
        setTimeout(res, durationMs + 30);
      });
    });
  };
})();
"""


# ── Branded intro / outro cards ───────────────────────────────────

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


def data_url(html: str) -> str:
    return "data:text/html;base64," + base64.b64encode(html.encode()).decode()


INTRO_URL = data_url(
    card_html(
        "DEMO GUIADA · 2026",
        "CheckWise",
        "Cumplimiento documental REPSE guiado, trazable y accionable. "
        "Tres roles, una plataforma. Esta es una demostración narrada.",
    )
)
OUTRO_URL = data_url(
    card_html(
        "GRACIAS",
        "checkwise.mx",
        "Reporte ejecutivo, expediente trazable, revisión humana "
        "obligatoria. Operado por Legal Shelf, en México.",
    )
)


# ── HTTP helpers ──────────────────────────────────────────────────

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


# ── Page helpers ──────────────────────────────────────────────────

def caption(page: Page, text: str, eyebrow: str | None = None) -> None:
    page.evaluate(
        "([t, e]) => window.__caption && window.__caption(t, e)",
        [text, eyebrow or "CHECKWISE · DEMO"],
    )


def caption_clear(page: Page) -> None:
    page.evaluate("() => window.__caption_clear && window.__caption_clear()")


def highlight(page: Page, selector: str, label: str | None = None) -> bool:
    return bool(
        page.evaluate(
            "([s, l]) => window.__highlight && window.__highlight(s, l)",
            [selector, label],
        )
    )


def spotlight(page: Page, selector: str, label: str | None = None) -> bool:
    return bool(
        page.evaluate(
            "([s, l]) => window.__spotlight && window.__spotlight(s, l)",
            [selector, label],
        )
    )


def unhighlight(page: Page) -> None:
    page.evaluate("() => window.__unhighlight && window.__unhighlight()")


def fade_out(page: Page, duration_ms: int = 320) -> None:
    page.evaluate(
        "(d) => window.__fade && window.__fade(true, d)", duration_ms
    )
    time.sleep(duration_ms / 1000 + 0.05)


def fade_in(page: Page, duration_ms: int = 320) -> None:
    page.evaluate(
        "(d) => window.__fade && window.__fade(false, d)", duration_ms
    )
    time.sleep(duration_ms / 1000 + 0.05)


def transition(page: Page, duration_ms: int = 280) -> None:
    """Quick fade-to-black-and-back at a scene boundary."""
    fade_out(page, duration_ms)
    fade_in(page, duration_ms)


def hover_smooth(page: Page, x: float, y: float, steps: int = 42) -> None:
    page.mouse.move(x, y, steps=steps)


def hover_element(page: Page, selector: str, steps: int = 42) -> tuple[float, float] | None:
    try:
        el = page.query_selector(selector)
    except Exception:
        return None
    if not el:
        return None
    box = el.bounding_box()
    if not box:
        return None
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    hover_smooth(page, cx, cy, steps=steps)
    return cx, cy


def click_element(page: Page, selector: str, steps: int = 42) -> None:
    coords = hover_element(page, selector, steps=steps)
    if coords:
        page.mouse.down()
        time.sleep(0.05)
        page.mouse.up()
    else:
        page.click(selector)


def type_into(page: Page, selector: str, text: str, delay_ms: int = 65) -> None:
    hover_element(page, selector, steps=18)
    page.focus(selector)
    time.sleep(0.18)
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


def dwell_to(page: Page, narration_seconds: float, *, used: float = 0.0) -> None:
    """Hold on screen until the scene's narration finishes (+tail)."""
    remaining = narration_seconds + SCENE_TAIL - used
    if remaining > 0:
        settle(page, remaining)


# ── Scenes (each consumes its named voice duration) ───────────────

def scene_intro(page: Page, d: dict) -> None:
    goto(page, INTRO_URL)
    dwell_to(page, d["intro"])


def scene_landing(page: Page, d: dict) -> None:
    t0 = time.time()
    goto(page, f"{APP}/")
    caption(page, "Hero claro y un solo CTA primario.", "ESCENA 1 · PÚBLICO")
    settle(page, 0.4)
    highlight(page, "h1", "Promesa en una frase")
    used = time.time() - t0
    dwell_to(page, d["landing"], used=used)
    unhighlight(page)
    caption_clear(page)


def scene_provider_login(page: Page, d: dict) -> None:
    t0 = time.time()
    goto(page, f"{APP}/login")
    caption(page, "Entramos como proveedor.", "ESCENA 2 · PROVEEDOR")
    settle(page, 0.6)
    # Highlight the subtitle the narrator references
    highlight(
        page,
        "p:has-text('credenciales')",
        "Si tu acceso es temporal, te pedimos rotar la contraseña",
    )
    settle(page, 3.5)
    unhighlight(page)
    type_into(page, "#login-email", "boss.demo@checkwise.mx", delay_ms=55)
    type_into(page, "#login-password", "BossDemo!2026", delay_ms=55)
    settle(page, 0.3)
    hover_element(page, "button[type='submit']")
    settle(page, 0.3)
    page.locator("button[type='submit']").click()
    page.wait_for_url("**/portal/entra-a-tu-espacio", timeout=15000)
    used = time.time() - t0
    dwell_to(page, d["provider_login"], used=used)
    caption_clear(page)


def scene_workspace_entry(page: Page, d: dict) -> None:
    t0 = time.time()
    caption(page, "Confirmación de identidad antes del dashboard.", "ESCENA 2 · PROVEEDOR")
    settle(page, 0.5)
    highlight(page, "h2:has-text('Confirma')", "Onramp humano")
    settle(page, 2.5)
    unhighlight(page)
    page.fill("#ws-first-name", "Marina")
    page.fill("#ws-last-name", "Quintero")
    settle(page, 0.6)
    hover_element(page, "form button[type='submit']")
    settle(page, 0.3)
    page.locator("form button[type='submit']").click()
    try:
        page.wait_for_url("**/portal/dashboard", timeout=20000)
    except Exception:
        goto(page, f"{APP}/portal/dashboard")
    used = time.time() - t0
    dwell_to(page, d["workspace_entry"], used=used)
    caption_clear(page)


def scene_provider_dashboard(page: Page, d: dict) -> None:
    t0 = time.time()
    caption(page, "El dashboard responde una sola pregunta: '¿qué sigue?'.", "ESCENA 3 · PROVEEDOR")
    settle(page, 0.8)
    # Spotlight 1: the next-action section header
    spotlight(page, "h2:has-text('TU SIGUIENTE')", "Centro de acción del proveedor")
    settle(page, 3.2)
    unhighlight(page)
    settle(page, 0.4)
    # Highlight 2: an individual action card to show the framing
    highlight(page, "article:has(button:has-text('Subir documento')), section:has(button:has-text('Subir documento')) >> nth=0", "Una tarjeta = un documento por subir")
    settle(page, 3.0)
    unhighlight(page)
    page.mouse.wheel(0, 240)
    settle(page, 0.8)
    used = time.time() - t0
    dwell_to(page, d["provider_dashboard"], used=used)
    caption_clear(page)


def scene_compliance_pulse(page: Page, d: dict) -> None:
    t0 = time.time()
    goto(page, f"{APP}/portal/reports")
    caption(page, "Compliance Pulse: 4 indicadores ejecutivos.", "ESCENA 4 · PROVEEDOR")
    settle(page, 0.8)
    # Spotlight the whole pulse section first
    spotlight(page, "section:has(h2:has-text('Pulso de cumplimiento'))", "¿Cómo estoy hoy?")
    settle(page, 5.5)
    unhighlight(page)
    settle(page, 0.4)
    used = time.time() - t0
    dwell_to(page, d["compliance_pulse"], used=used)
    caption_clear(page)


def scene_report_editor(page: Page, d: dict, report_id: str) -> None:
    t0 = time.time()
    goto(page, f"{APP}/portal/reports/{report_id}")
    caption(page, "Editor con IA + copiloto + 'Actualizar con datos de hoy'.", "ESCENA 5 · REPORTES")
    settle(page, 0.8)
    highlight(page, "a:has-text('Vista previa PDF')", "Toolbar de exportación PDF")
    settle(page, 4.5)
    unhighlight(page)
    hover_element(page, "a:has-text('Vista previa PDF')")
    settle(page, 0.6)
    used = time.time() - t0
    dwell_to(page, d["report_editor"], used=used)
    caption_clear(page)


def scene_print_page(page: Page, d: dict, report_id: str) -> None:
    t0 = time.time()
    goto(page, f"{APP}/portal/reports/{report_id}/print")
    caption(page, "Reporte imprimible: cabecera, paginación, sello.", "ESCENA 6 · PDF")
    settle(page, 1.0)
    # Spotlight the freshness seal (most P1.8-distinctive feature)
    spotlight(page, ".cw-print-seal", "Sello 'Datos al…' en cada copia impresa")
    settle(page, 4.5)
    unhighlight(page)
    settle(page, 0.4)
    # Then a quick highlight on the toolbar
    highlight(page, ".cw-print-toolbar button", "Un clic → Guardar como PDF")
    settle(page, 3.0)
    unhighlight(page)
    used = time.time() - t0
    dwell_to(page, d["print_page"], used=used)
    caption_clear(page)


def scene_client_login(page: Page, d: dict) -> None:
    t0 = time.time()
    fade_out(page, 320)
    page.evaluate("() => window.localStorage.clear()")
    goto(page, f"{APP}/login")
    fade_in(page, 320)
    caption(page, "Cambio de rol: ahora como cliente.", "ESCENA 7 · CLIENTE")
    settle(page, 0.6)
    type_into(page, "#login-email", "cliente.demo@checkwise.mx", delay_ms=50)
    type_into(page, "#login-password", "ClienteDemo!2026", delay_ms=50)
    settle(page, 0.3)
    hover_element(page, "button[type='submit']")
    settle(page, 0.3)
    page.locator("button[type='submit']").click()
    page.wait_for_url("**/client/dashboard", timeout=15000)
    used = time.time() - t0
    dwell_to(page, d["client_login"], used=used)
    caption_clear(page)


def scene_client_dashboard(page: Page, d: dict) -> None:
    t0 = time.time()
    caption(page, "Titular ejecutivo en una sola frase.", "ESCENA 8 · CLIENTE")
    settle(page, 0.8)
    spotlight(page, "h2:has-text('proveedores')", "Lectura ejecutiva de 3 segundos")
    settle(page, 5.0)
    unhighlight(page)
    settle(page, 0.4)
    used = time.time() - t0
    dwell_to(page, d["client_dashboard"], used=used)
    caption_clear(page)


def scene_vendor_detail(page: Page, d: dict, vendor_id: str) -> None:
    t0 = time.time()
    goto(page, f"{APP}/client/vendors/{vendor_id}")
    caption(page, "Narrativa de 6 secciones por proveedor.", "ESCENA 9 · CLIENTE")
    settle(page, 1.0)
    highlight(page, "h2:has-text('ACCIONES SUGERIDAS')", "Sección 1 de 6")
    settle(page, 3.5)
    unhighlight(page)
    highlight(page, "h2:has-text('DOCUMENTOS POR ESTADO')", "Sección 4 de 6")
    settle(page, 3.0)
    unhighlight(page)
    used = time.time() - t0
    dwell_to(page, d["vendor_detail"], used=used)
    caption_clear(page)


def scene_admin_login(page: Page, d: dict) -> None:
    t0 = time.time()
    fade_out(page, 320)
    page.evaluate("() => window.localStorage.clear()")
    goto(page, f"{APP}/login")
    fade_in(page, 320)
    caption(page, "Tercer rol: revisor interno de Legal Shelf.", "ESCENA 10 · REVISOR")
    settle(page, 0.6)
    type_into(page, "#login-email", "ada@legalshelf.mx", delay_ms=55)
    type_into(page, "#login-password", "demo1234", delay_ms=55)
    settle(page, 0.3)
    hover_element(page, "button[type='submit']")
    settle(page, 0.3)
    page.locator("button[type='submit']").click()
    page.wait_for_url("**/admin/reviewer", timeout=15000)
    used = time.time() - t0
    dwell_to(page, d["admin_login"], used=used)
    caption_clear(page)


def scene_reviewer_queue(page: Page, d: dict) -> None:
    t0 = time.time()
    caption(page, "Doctrina del producto: ningún documento auto-aprueba.", "ESCENA 11 · REVISOR")
    settle(page, 0.6)
    spotlight(page, "h1:has-text('Documentos por revisar') + p", "La automatización no firma. El revisor decide.")
    settle(page, 5.5)
    unhighlight(page)
    used = time.time() - t0
    dwell_to(page, d["reviewer_queue"], used=used)
    caption_clear(page)


def scene_reviewer_detail(page: Page, d: dict, submission_id: str) -> None:
    t0 = time.time()
    goto(page, f"{APP}/admin/reviewer/{submission_id}")
    caption(page, "Cuatro acciones explícitas + bitácora de trazabilidad.", "ESCENA 12 · REVISOR")
    settle(page, 1.0)
    spotlight(page, "h2:has-text('Tu decisión'), h3:has-text('Tu decisión'), h2:has-text('TU DECISIÓN'), h3:has-text('TU DECISIÓN')", "Aprobar · Rechazar · Aclarar · Excepción")
    settle(page, 5.5)
    unhighlight(page)
    used = time.time() - t0
    dwell_to(page, d["reviewer_detail"], used=used)
    caption_clear(page)


def scene_outro(page: Page, d: dict) -> None:
    fade_out(page, 400)
    goto(page, OUTRO_URL)
    fade_in(page, 400)
    dwell_to(page, d["outro"])
    fade_out(page, 500)


# ── Main ──────────────────────────────────────────────────────────

def run(pw: Playwright) -> Path:
    for f in RAW_DIR.glob("*.webm"):
        f.unlink()

    durations = load_durations()
    total = sum(durations.values()) + SCENE_TAIL * len(durations)
    print(f"Target runtime: ~{total:.1f}s\n")

    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport=VIEWPORT,
        locale="es-MX",
        record_video_dir=str(RAW_DIR),
        record_video_size=VIDEO_SIZE,
    )
    ctx.add_init_script(INJECT_JS)
    page = ctx.new_page()

    # Pre-fetch the report + vendor + submission IDs we'll need.
    prov_token = login(*ACCOUNTS["provider"])["access_token"]
    reports = list_reports(prov_token)
    report_id = next(
        (r["id"] for r in reports if r.get("audience") == "vendor_facing"),
        reports[0]["id"] if reports else None,
    )

    cli_token = login(*ACCOUNTS["client"])["access_token"]
    vendors = list_vendors(cli_token)
    vendor_id = (vendors[0].get("id") or vendors[0].get("vendor_id")) if vendors else None

    adm_token = login(*ACCOUNTS["admin"])["access_token"]
    queue = reviewer_queue(adm_token)
    submission_id = queue[0]["submission_id"] if queue else None

    scenes = [
        ("intro", lambda: scene_intro(page, durations)),
        ("landing", lambda: scene_landing(page, durations)),
        ("provider_login", lambda: scene_provider_login(page, durations)),
        ("workspace_entry", lambda: scene_workspace_entry(page, durations)),
        ("provider_dashboard", lambda: scene_provider_dashboard(page, durations)),
        ("compliance_pulse", lambda: scene_compliance_pulse(page, durations)),
        ("report_editor", lambda: scene_report_editor(page, durations, report_id)),
        ("print_page", lambda: scene_print_page(page, durations, report_id)),
        ("client_login", lambda: scene_client_login(page, durations)),
        ("client_dashboard", lambda: scene_client_dashboard(page, durations)),
        ("vendor_detail", lambda: scene_vendor_detail(page, durations, vendor_id)),
        ("admin_login", lambda: scene_admin_login(page, durations)),
        ("reviewer_queue", lambda: scene_reviewer_queue(page, durations)),
        ("reviewer_detail", lambda: scene_reviewer_detail(page, durations, submission_id)),
        ("outro", lambda: scene_outro(page, durations)),
    ]
    for name, fn in scenes:
        target = durations[name] + SCENE_TAIL
        print(f"→ {name:24s} ({target:5.1f}s)")
        fn()

    ctx.close()
    browser.close()

    webms = sorted(RAW_DIR.glob("*.webm"))
    if not webms:
        raise SystemExit("no video produced")
    return webms[0]


def encode_silent_mp4(webm: Path) -> Path:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not on PATH; brew install ffmpeg")
    print(f"→ Encoding {webm.name} → silent MP4")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(webm),
        "-vf", "scale=1920:1080:flags=lanczos",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(SILENT_MP4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    dur = float(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(SILENT_MP4)],
            text=True,
        ).strip()
    )
    size_mb = SILENT_MP4.stat().st_size / (1024 * 1024)
    print(f"✓ {SILENT_MP4.relative_to(ROOT)}  ({dur:.1f}s · {size_mb:.1f} MB)")
    return SILENT_MP4


if __name__ == "__main__":
    with sync_playwright() as pw:
        webm = run(pw)
    encode_silent_mp4(webm)
    print("\n→ Next: backend/.venv/bin/python scripts/finalize_demo.py")
