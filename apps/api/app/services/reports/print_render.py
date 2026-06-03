"""Designed, print-optimized report document (server-side).

Renders a report's ``content_json`` into a polished, document-style HTML page —
the verdict hero, the key findings, clean compliance bars, the by-institution
breakdown, the vendor matrix table, the recommendation — NOT the generic
key/value data dump in ``export.render_report_html``. Chromium turns this into
a clean, one-click PDF (see ``export.render_report_pdf``).

Self-contained: no external assets, all CSS inline, renders purely from the
block data the backend already has — so it needs no auth, no frontend, and is
identical every time.
"""

from __future__ import annotations

import html as _html
from typing import Any

from app.constants.reports import ReportAudience
from app.models import Report, ReportVersion
from app.models.entities import utc_now

# ─── Palette ───────────────────────────────────────────────────
_BRAND = "#013557"
_ACCENT = "#09c1b0"
_RED = "#dc2626"
_AMBER = "#d97706"
_GREEN = "#16a34a"
_INK = "#0f172a"
_MUTED = "#475569"
_FAINT = "#94a3b8"
_LINE = "#e2e8f0"
_SURFACE = "#ffffff"
_SURFACE_2 = "#f8fafc"

_LEVEL_COLOR = {"red": _RED, "yellow": _AMBER, "green": _GREEN}
_LEVEL_WORD = {"red": "Riesgo", "yellow": "Atención", "green": "En regla"}
_TONE_COLOR = {"red": _RED, "yellow": _AMBER, "green": _GREEN, "info": _BRAND}

# matrix cell document-state → (label, color)
_CELL = {
    "approved": ("Aprobado", _GREEN),
    "in_review": ("En revisión", _AMBER),
    "needs_review": ("Observación", _AMBER),
    "uploaded": ("Recibido", _AMBER),
    "rejected": ("Rechazado", _RED),
    "expired": ("Vencido", _RED),
    "pending": ("Por entregar", _FAINT),
    "empty": ("—", _FAINT),
}
_SLOT_LABEL = {
    "rejected": "Rechazado",
    "needs_correction": "Requiere aclaración",
    "possible_mismatch": "Posible inconsistencia",
    "expired": "Vencido",
    "missing": "Faltante",
    "in_review": "En revisión",
    "uploaded": "Recibido",
}


def _e(v: Any) -> str:
    return _html.escape("" if v is None else str(v))


def _audience_label(a: str | None) -> str:
    return {
        ReportAudience.CLIENT_FACING.value: "Cliente",
        ReportAudience.VENDOR_FACING.value: "Proveedor",
        ReportAudience.INTERNAL_ONLY.value: "Interno",
    }.get(a or "", a or "—")


# ─── Small visual primitives ───────────────────────────────────


def _bar(pct: float, color: str, *, height: int = 8) -> str:
    pct = max(0, min(100, float(pct or 0)))
    return (
        f'<div style="background:{_LINE};border-radius:999px;height:{height}px;overflow:hidden">'
        f'<div style="width:{pct:.0f}%;height:100%;background:{color};border-radius:999px"></div></div>'
    )


def _stacked_bar(segments: list[tuple[float, str]]) -> str:
    total = sum(max(0, s[0]) for s in segments) or 1
    cells = "".join(
        f'<div style="width:{(v/total)*100:.1f}%;background:{c}"></div>'
        for v, c in segments if v > 0
    )
    return (
        '<div style="display:flex;height:9px;border-radius:999px;overflow:hidden;'
        f'background:{_LINE}">{cells}</div>'
    )


def _donut(green: int, yellow: int, red: int, *, size: int = 96) -> str:
    total = green + yellow + red or 1
    r = 16
    circ = 2 * 3.14159 * r
    parts = []
    offset = 0.0
    for val, col in ((green, _GREEN), (yellow, _AMBER), (red, _RED)):
        frac = val / total
        dash = frac * circ
        parts.append(
            f'<circle cx="18" cy="18" r="{r}" fill="none" stroke="{col}" '
            f'stroke-width="5" stroke-dasharray="{dash:.2f} {circ - dash:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 18 18)"/>'
        )
        offset += dash
    pct = round(100 * green / total)
    return (
        f'<svg viewBox="0 0 36 36" width="{size}" height="{size}">'
        f'<circle cx="18" cy="18" r="{r}" fill="none" stroke="{_LINE}" stroke-width="5"/>'
        + "".join(parts)
        + f'<text x="18" y="19" text-anchor="middle" font-size="7" font-weight="700" '
        f'fill="{_INK}">{pct}%</text>'
        f'<text x="18" y="24.5" text-anchor="middle" font-size="2.6" fill="{_MUTED}">CUMPL.</text>'
        "</svg>"
    )


def _eyebrow(text: str) -> str:
    return f'<p class="eyebrow">{_e(text)}</p>'


# ─── Per-block renderers ───────────────────────────────────────


def _r_verdict(data: dict) -> str:
    v = (data or {}).get("verdict") or {}
    level = v.get("level", "yellow")
    color = _LEVEL_COLOR.get(level, _AMBER)
    metric = v.get("metric") or {}
    mval = metric.get("value", "")
    mtxt = f"{mval}%" if metric.get("format") == "percent" else f"{mval}"
    trend = v.get("trend")
    trend_html = ""
    if isinstance(trend, int) and trend != 0:
        tcol = _GREEN if trend > 0 else _RED
        arrow = "▲" if trend > 0 else "▼"
        sign = "+" if trend > 0 else ""
        trend_html = (
            f'<div style="margin-top:4px;font-size:10px;font-weight:700;color:{tcol}">'
            f'{arrow} {sign}{trend} pts <span style="color:{_FAINT};font-weight:400">vs. mes ant.</span></div>'
        )
    return (
        f'<section class="block verdict" style="border-left:5px solid {color}">'
        '<div class="verdict-row">'
        "<div>"
        f'<p class="chip" style="color:{color}">● {_e(_LEVEL_WORD.get(level, "Atención"))}</p>'
        f'<h2 class="verdict-head">{_e(v.get("headline"))}</h2>'
        f'<p class="verdict-sub">{_e(v.get("subhead"))}</p>'
        "</div>"
        '<div class="verdict-metric">'
        f'<div class="metric-num">{_e(mtxt)}</div>'
        f'<div class="metric-label">{_e(metric.get("label"))}</div>{trend_html}</div>'
        "</div></section>"
    )


def _r_findings(data: dict) -> str:
    items = (data or {}).get("findings") or []
    if not items:
        return ""
    rows = []
    for f in items:
        col = _TONE_COLOR.get(f.get("tone"), _BRAND)
        rows.append(
            '<li class="finding">'
            f'<span class="dot" style="background:{col}"></span>'
            "<div>"
            f'<p class="finding-title">{_e(f.get("title"))}</p>'
            f'<p class="finding-detail">{_e(f.get("detail"))}</p></div></li>'
        )
    return (
        '<section class="block">' + _eyebrow("Lo más importante")
        + '<ul class="findings">' + "".join(rows) + "</ul></section>"
    )


def _r_overview(data: dict) -> str:
    if not data:
        return ""
    sem = data.get("vendors_semaphore") or {}
    crit = data.get("docs_critical_breakdown") or {}
    kpis = [
        (f'{data.get("overall_compliance_pct", 0)}%', "Cumplimiento global"),
        (str(data.get("vendors_total", 0)), "Proveedores"),
        (str(data.get("docs_critical", 0)), "Documentos críticos"),
        (str(data.get("docs_in_review", 0)), "En revisión"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-num">{_e(val)}</div>'
        f'<div class="kpi-label">{_e(lbl)}</div></div>'
        for val, lbl in kpis
    )
    bars = []
    for v in (data.get("by_vendor") or [])[:12]:
        col = _LEVEL_COLOR.get(v.get("semaphore_level"), _AMBER)
        bars.append(
            '<div class="vrow">'
            f'<div class="vname">{_e(v.get("vendor_name"))}</div>'
            f'<div class="vbar">{_bar(v.get("compliance_pct", 0), col)}</div>'
            f'<div class="vpct">{_e(v.get("compliance_pct", 0))}%</div></div>'
        )
    return (
        '<section class="block">' + _eyebrow("Cifras clave del portafolio")
        + f'<div class="kpis">{kpi_html}</div>'
        + (f'<p class="micro">Semáforo: {sem.get("green",0)} al día · '
           f'{sem.get("yellow",0)} en proceso · {sem.get("red",0)} en riesgo · '
           f'críticos: {crit.get("rechazados",0)} rechazados, {crit.get("inconsistencias",0)} inconsistencias, '
           f'{crit.get("vencidos",0)} vencidos</p>')
        + (f'<p class="sublabel">Cumplimiento por proveedor</p><div class="vrows">{"".join(bars)}</div>'
           if bars else "")
        + "</section>"
    )


def _r_by_institution(data: dict) -> str:
    insts = (data or {}).get("institutions") or []
    if not insts:
        return ""
    rows = []
    for i in insts:
        segs = [(i.get("al_dia", 0), _GREEN), (i.get("en_proceso", 0), _AMBER), (i.get("en_riesgo", 0), _RED)]
        risk = i.get("en_riesgo", 0)
        risk_txt = f' · <span style="color:{_RED};font-weight:600">{risk} en riesgo</span>' if risk else ""
        rows.append(
            '<div class="irow">'
            f'<div class="iname">{_e(i.get("label"))}</div>'
            f'<div class="ibar">{_stacked_bar(segs)}</div>'
            f'<div class="itot">{_e(i.get("total",0))}{risk_txt}</div></div>'
        )
    return (
        '<section class="block">' + _eyebrow("Cumplimiento por institución")
        + f'<div class="irows">{"".join(rows)}</div>'
        + '<p class="legend"><span class="lg" style="background:'+_GREEN+'"></span>Al día'
          '<span class="lg" style="background:'+_AMBER+'"></span>En proceso'
          '<span class="lg" style="background:'+_RED+'"></span>En riesgo</p>'
        + "</section>"
    )


def _r_radar(data: dict) -> str:
    if not data:
        return ""
    sc = data.get("semaphore_counts") or {}
    return (
        '<section class="block">' + _eyebrow("Radar de cumplimiento")
        + '<div class="radar">'
        + _donut(sc.get("green", 0), sc.get("yellow", 0), sc.get("red", 0))
        + '<div class="radar-legend">'
        + f'<p><span class="lg" style="background:{_GREEN}"></span>Verde · {sc.get("green",0)}</p>'
        + f'<p><span class="lg" style="background:{_AMBER}"></span>Amarillo · {sc.get("yellow",0)}</p>'
        + f'<p><span class="lg" style="background:{_RED}"></span>Rojo · {sc.get("red",0)}</p>'
        + f'<p class="micro">{data.get("vendor_count",0)} proveedores · {data.get("overall_compliance_pct",0)}% global</p>'
        + "</div></div></section>"
    )


def _r_matrix(data: dict) -> str:
    rows = (data or {}).get("rows") or []
    if not rows:
        return ""
    cols = ["sat", "imss", "infonavit", "stps_repse"]
    head = "".join(f"<th>{c.upper().replace('_','-')}</th>" for c in cols)
    body = []
    for r in rows:
        cells = []
        for c in cols:
            st = (r.get("cells") or {}).get(c, {}).get("state", "empty")
            lbl, col = _CELL.get(st, ("—", _FAINT))
            cells.append(f'<td style="color:{col};font-weight:600">{_e(lbl)}</td>')
        body.append(
            "<tr>"
            f'<td class="vcell"><div class="vc-name">{_e(r.get("vendor_name"))}</div>'
            f'<div class="vc-rfc">{_e(r.get("vendor_rfc"))}</div></td>'
            + "".join(cells)
            + f'<td class="risk">{_e(r.get("risk_score",0))}</td></tr>'
        )
    return (
        '<section class="block">' + _eyebrow("Matriz de riesgo por proveedor")
        + f'<table class="matrix"><thead><tr><th>Proveedor</th>{head}<th>Riesgo</th></tr></thead>'
        + f'<tbody>{"".join(body)}</tbody></table></section>'
    )


def _r_compliance_state(data: dict) -> str:
    sem = (data or {}).get("semaphore") or {}
    counts = (data or {}).get("document_state_counts") or {}
    level = sem.get("level", "yellow")
    order = [("approved", "Aprobados"), ("in_review", "En revisión"), ("rejected", "Rechazados"),
             ("needs_review", "Observación"), ("expired", "Vencidos"), ("pending", "Por entregar")]
    chips = "".join(
        f'<div class="sc"><span class="sc-n">{_e(counts.get(k,0))}</span>'
        f'<span class="sc-l">{_e(lbl)}</span></div>'
        for k, lbl in order if counts.get(k)
    )
    return (
        f'<section class="block verdict" style="border-left:5px solid {_LEVEL_COLOR.get(level,_AMBER)}">'
        '<div class="verdict-row"><div>'
        f'<p class="chip" style="color:{_LEVEL_COLOR.get(level,_AMBER)}">● {_e(sem.get("label","Estado"))}</p>'
        f'<p class="verdict-sub">{_e(sem.get("reason",""))}</p></div>'
        f'<div class="verdict-metric"><div class="metric-num">{_e(sem.get("compliance_pct",0))}%</div>'
        '<div class="metric-label">Cumplimiento</div></div></div>'
        f'<div class="scs">{chips}</div></section>'
    )


def _r_attention(data: dict) -> str:
    items = (data or {}).get("items") or []
    if not items:
        return ""
    rows = []
    for it in items[:14]:
        st = it.get("state", "")
        lbl = _SLOT_LABEL.get(st, st)
        due = it.get("due_in_days")
        due_txt = (f"vence en {due} d" if isinstance(due, int) and due >= 0
                   else f"vencido" if isinstance(due, int) else "")
        rows.append(
            "<tr>"
            f'<td>{_e(str(it.get("institution","")).upper())}</td>'
            f'<td>{_e(it.get("title"))}</td>'
            f'<td>{_e(lbl)}</td><td class="num">{_e(due_txt)}</td></tr>'
        )
    return (
        '<section class="block">' + _eyebrow("Documentos por atender")
        + f'<table class="list"><tbody>{"".join(rows)}</tbody></table></section>'
    )


def _r_deadlines(data: dict) -> str:
    items = (data or {}).get("items") or []
    if not items:
        return ""
    rows = []
    for it in items[:10]:
        due = it.get("due_in_days")
        due_txt = f"en {due} d" if isinstance(due, int) and due >= 0 else ("vencido" if isinstance(due, int) else "")
        rows.append(
            "<tr>"
            f'<td>{_e(str(it.get("institution","")).upper())}</td>'
            f'<td>{_e(it.get("title"))}</td><td class="num">{_e(due_txt)}</td></tr>'
        )
    return (
        '<section class="block">' + _eyebrow("Próximos vencimientos")
        + f'<table class="list"><tbody>{"".join(rows)}</tbody></table></section>'
    )


def _r_actions(data: dict) -> str:
    items = (data or {}).get("items") or (data or {}).get("actions") or []
    if not items:
        return ""
    cards = []
    for n, a in enumerate(items[:5], start=1):
        cards.append(
            '<li class="action">'
            f'<span class="anum">{n}</span><div>'
            f'<p class="finding-title">{_e(a.get("title"))}</p>'
            f'<p class="finding-detail">{_e(a.get("body") or a.get("detail") or "")}</p></div></li>'
        )
    return (
        '<section class="block">' + _eyebrow("Acciones priorizadas")
        + f'<ul class="findings">{"".join(cards)}</ul></section>'
    )


def _r_kpi(block: dict) -> str:
    cfg = block.get("config") or {}
    resolved = {m["metric_key"]: m for m in ((block.get("data") or {}).get("resolved") or [])}
    cards = []
    for m in cfg.get("metrics") or []:
        rv = resolved.get(m.get("metric_key"), {})
        val = rv.get("value", "—")
        txt = f"{val}%" if m.get("format") == "percent" else f"{val}"
        cards.append(
            f'<div class="kpi"><div class="kpi-num">{_e(txt)}</div>'
            f'<div class="kpi-label">{_e(m.get("label"))}</div></div>'
        )
    return f'<section class="block"><div class="kpis">{"".join(cards)}</div></section>' if cards else ""


def _r_text(block: dict) -> str:
    cfg = block.get("config") or {}
    heading = cfg.get("heading")
    body = cfg.get("body") or (block.get("data") or {}).get("body") or ""
    paras = "".join(f"<p>{_e(p.strip())}</p>" for p in str(body).split("\n") if p.strip())
    head = f"<h3>{_e(heading)}</h3>" if heading else ""
    return f'<section class="block text">{head}{paras}</section>' if (head or paras) else ""


def _r_exec_summary(data: dict) -> str:
    s = (data or {}).get("summary")
    return f'<section class="block text"><p>{_e(s)}</p></section>' if s else ""


_RENDERERS = {
    "report_verdict": lambda b: _r_verdict(b.get("data") or {}),
    "key_findings": lambda b: _r_findings(b.get("data") or {}),
    "compliance_overview": lambda b: _r_overview(b.get("data") or {}),
    "compliance_by_institution": lambda b: _r_by_institution(b.get("data") or {}),
    "compliance_radar": lambda b: _r_radar(b.get("data") or {}),
    "vendor_risk_matrix": lambda b: _r_matrix(b.get("data") or {}),
    "compliance_state": lambda b: _r_compliance_state(b.get("data") or {}),
    "attention_list": lambda b: _r_attention(b.get("data") or {}),
    "upcoming_deadlines": lambda b: _r_deadlines(b.get("data") or {}),
    "prioritized_actions": lambda b: _r_actions(b.get("data") or {}),
    "kpi_strip": _r_kpi,
    "text": _r_text,
    "executive_summary": lambda b: _r_exec_summary(b.get("data") or {}),
    "divider": lambda b: '<hr class="divider"/>',
}


def _block_html(block: dict) -> str:
    fn = _RENDERERS.get(str(block.get("type")))
    if fn is None:
        return ""
    try:
        return fn(block)
    except Exception:  # noqa: BLE001 — one bad block must not sink the document
        return ""


def render_report_document_html(report: Report, version: ReportVersion) -> bytes:
    content = version.content_json or {}
    blocks = content.get("blocks") or []
    title = _e(report.title or "Reporte CheckWise")
    desc = _e(report.description or "")
    generated = utc_now().strftime("%d/%m/%Y %H:%M")
    body = "".join(_block_html(b) for b in blocks)

    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>{title}</title><style>{_STYLE}</style></head><body><main class="page">
<header class="cover">
  <div class="brand">CheckWise</div>
  <p class="cover-eyebrow">Reporte de cumplimiento REPSE</p>
  <h1>{title}</h1>
  {f'<p class="cover-desc">{desc}</p>' if desc else ''}
  <div class="cover-meta">
    <span><b>Audiencia</b> {_e(_audience_label(report.audience))}</span>
    <span><b>Versión</b> v{version.version_number}</span>
    <span><b>Generado</b> {generated}</span>
  </div>
</header>
{body}
<footer class="foot">Generado por CheckWise · {generated} · Powered by Legal Shelf</footer>
</main></body></html>"""
    return doc.encode("utf-8")


_STYLE = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
@page{{size:Letter;margin:14mm}}
html,body{{font-family:-apple-system,'Segoe UI','Helvetica Neue',Arial,sans-serif;
  color:{_INK};font-size:12px;line-height:1.5;background:{_SURFACE}}}
.page{{max-width:760px;margin:0 auto}}
.eyebrow{{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:{_FAINT};
  font-weight:600;margin-bottom:6px}}
.cover{{background:{_BRAND};color:#fff;border-radius:12px;padding:26px 28px;margin-bottom:22px}}
.cover .brand{{font-weight:700;letter-spacing:.02em;font-size:15px;color:{_ACCENT}}}
.cover-eyebrow{{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:#9fd9d3;margin-top:14px}}
.cover h1{{font-size:24px;font-weight:700;margin-top:6px;line-height:1.15}}
.cover-desc{{color:#cdd8e2;font-size:12px;margin-top:8px;max-width:46em}}
.cover-meta{{margin-top:18px;padding-top:14px;border-top:1px solid rgba(255,255,255,.18);
  display:flex;gap:26px;font-size:10px;color:#cdd8e2}}
.cover-meta b{{display:block;color:#9fd9d3;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;font-size:9px;margin-bottom:2px}}
.block{{margin-bottom:18px;break-inside:avoid}}
.divider{{border:0;border-top:1px solid {_LINE};margin:18px 0}}
.text h3{{font-size:14px;font-weight:600;margin-bottom:5px;color:{_INK}}}
.text p{{margin-bottom:6px;color:{_INK}}}
/* verdict */
.verdict{{border:1px solid {_LINE};border-radius:10px;padding:16px 18px;background:{_SURFACE}}}
.verdict-row{{display:flex;justify-content:space-between;align-items:center;gap:18px}}
.chip{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px}}
.verdict-head{{font-size:19px;font-weight:700;line-height:1.15}}
.verdict-sub{{color:{_MUTED};font-size:12px;margin-top:3px}}
.verdict-metric{{text-align:right;white-space:nowrap}}
.metric-num{{font-size:30px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums}}
.metric-label{{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:{_FAINT};margin-top:3px}}
.scs{{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px;padding-top:12px;border-top:1px solid {_LINE}}}
.sc{{display:flex;flex-direction:column}}
.sc-n{{font-weight:700;font-size:15px}}
.sc-l{{font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:{_FAINT}}}
/* findings + actions */
.findings{{list-style:none;display:flex;flex-direction:column;gap:8px}}
.finding,.action{{display:flex;gap:10px;align-items:flex-start;border:1px solid {_LINE};
  border-radius:8px;padding:10px 12px;break-inside:avoid}}
.dot{{width:9px;height:9px;border-radius:999px;margin-top:5px;flex:none}}
.anum{{width:18px;height:18px;border-radius:999px;background:{_BRAND};color:#fff;font-size:10px;
  font-weight:700;display:flex;align-items:center;justify-content:center;flex:none;margin-top:1px}}
.finding-title{{font-weight:600;font-size:12.5px}}
.finding-detail{{color:{_MUTED};font-size:11.5px;margin-top:1px}}
/* kpis */
.kpis{{display:flex;gap:24px;flex-wrap:wrap}}
.kpi-num{{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}}
.kpi-label{{font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:{_FAINT};margin-top:2px}}
.micro{{font-size:10px;color:{_MUTED};margin-top:8px}}
.sublabel{{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:{_FAINT};margin:12px 0 6px}}
/* vendor rows */
.vrows,.irows{{display:flex;flex-direction:column;gap:6px}}
.vrow,.irow{{display:flex;align-items:center;gap:10px;font-size:11px}}
.vname,.iname{{width:170px;flex:none;color:{_INK};overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.vbar,.ibar{{flex:1}}
.vpct{{width:38px;text-align:right;font-variant-numeric:tabular-nums;color:{_MUTED}}}
.itot{{width:120px;text-align:right;font-variant-numeric:tabular-nums;color:{_MUTED}}}
.legend{{font-size:9px;color:{_MUTED};margin-top:8px}}
.lg{{display:inline-block;width:8px;height:8px;border-radius:2px;margin:0 4px 0 10px;vertical-align:middle}}
.legend .lg:first-child{{margin-left:0}}
/* radar */
.radar{{display:flex;align-items:center;gap:22px}}
.radar-legend p{{font-size:11px;color:{_INK};margin-bottom:3px}}
/* matrix table */
table{{width:100%;border-collapse:collapse;font-size:10.5px}}
.matrix th,.matrix td{{text-align:left;padding:6px 8px;border-bottom:1px solid {_LINE}}}
.matrix th{{font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:{_FAINT};font-weight:600}}
.matrix .risk{{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}}
.vc-name{{font-weight:600;color:{_INK}}}
.vc-rfc{{font-size:9px;color:{_FAINT}}}
.list td{{padding:5px 8px;border-bottom:1px solid {_LINE}}}
.list .num{{text-align:right;color:{_MUTED};white-space:nowrap}}
.foot{{margin-top:20px;padding-top:12px;border-top:1px solid {_LINE};text-align:center;
  font-size:9px;color:{_FAINT}}}
@media print{{.cover{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  .block,.finding,.action,.verdict{{break-inside:avoid}}}}
"""


__all__ = ["render_report_document_html"]
