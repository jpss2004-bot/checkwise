"""INDICE.pdf cover for the audit-package ZIP.

Junta 2026-05-23 — the ZIP we hand to the auditor must open with a
self-explanatory cover so the auditor can see scope and contents at
a glance without depending on the client_admin to walk them
through it.

The cover renders as a single self-contained HTML document and is
turned into a PDF via headless Chromium (the same pipeline
:mod:`app.services.reports.export` uses for executive reports).
Render-time inputs are the resolved
:class:`app.services.audit_package.AuditPackageEntry` rows plus the
filter context — so the index is guaranteed to match what the ZIP
actually contains.

Imports of ``playwright`` and ``tempfile`` are deferred to the call
site so module load stays cheap for processes that never render PDFs.
"""

from __future__ import annotations

import html
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.models import Client
from app.services.audit_package import AuditPackageEntry, AuditPackageFilters

logger = logging.getLogger("checkwise.audit_package_manifest")

# Spanish labels for the institutions we know about. Falls back to
# the raw code when an unknown institution appears.
_INSTITUTION_LABELS: dict[str, str] = {
    "sat": "SAT",
    "imss": "IMSS",
    "infonavit": "INFONAVIT",
    "stps_repse": "STPS / REPSE",
    "interno_cliente": "Interno cliente",
}

# Spanish labels for the canonical document statuses. Mirrors the
# frontend RequirementStatusBadge map so a forensic comparison stays
# in lockstep.
_STATUS_LABELS: dict[str, str] = {
    "aprobado": "Aprobado",
    "rechazado": "Requiere corrección",
    "requiere_aclaracion": "Necesita aclaración",
    "pendiente_revision": "En revisión humana",
    "prevalidado": "Prevalidado",
    "posible_mismatch": "Posible inconsistencia",
    "recibido": "Recibido",
    "vencido": "Vencido",
    "no_aplica": "No aplica",
    "excepcion_legal": "Excepción legal",
    "pendiente": "Pendiente",
}


def render_audit_manifest(
    *,
    client: Client,
    filters: AuditPackageFilters,
    entries: list[AuditPackageEntry],
    generated_at: datetime | None = None,
) -> bytes:
    """Render the cover index as PDF bytes.

    Steps:
      1. Build a self-contained HTML document (no external assets;
         all CSS inline so chromium has nothing to fetch).
      2. Write to a tempfile.
      3. Launch headless chromium, ``page.goto("file://...")``,
         ``page.pdf()`` with conservative print settings.
      4. Unlink the tempfile and return the bytes.

    ``generated_at`` defaults to ``datetime.now(UTC)``; tests pass a
    fixed value to make snapshots stable.
    """
    from playwright.sync_api import sync_playwright

    html_bytes = _render_manifest_html(
        client=client,
        filters=filters,
        entries=entries,
        generated_at=generated_at or datetime.now(UTC),
    )

    tmp = tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, prefix="cw-audit-indice-"
    )
    try:
        tmp.write(html_bytes)
        tmp.close()
        tmp_path = Path(tmp.name)
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page()
                page.goto(f"file://{tmp_path}", wait_until="networkidle")
                pdf_bytes = page.pdf(
                    format="Letter",
                    print_background=True,
                    margin={
                        "top": "0.5in",
                        "right": "0.5in",
                        "bottom": "0.5in",
                        "left": "0.5in",
                    },
                )
            finally:
                browser.close()
        return pdf_bytes
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:  # pragma: no cover — defensive cleanup
            logger.warning(
                "[audit_manifest] failed to delete temp file %s", tmp.name
            )


def _render_manifest_html(
    *,
    client: Client,
    filters: AuditPackageFilters,
    entries: list[AuditPackageEntry],
    generated_at: datetime,
) -> bytes:
    """Compose the self-contained HTML the renderer consumes.

    Pure function — exposed (not private with ``__name__`` mangling)
    so the test suite can snapshot the HTML without spinning up
    Playwright. Returns ``utf-8`` encoded bytes ready to write to
    disk.
    """
    title = "Paquete para auditoría · CheckWise"
    client_name = html.escape(client.name or "Cliente")
    client_rfc = html.escape(client.rfc or "—")
    generated_label = generated_at.astimezone(UTC).strftime("%d/%m/%Y %H:%M UTC")

    # Scope summary
    period_label = _format_period_range(filters)
    institution_label = (
        ", ".join(
            _INSTITUTION_LABELS.get(code, code.upper())
            for code in filters.institutions
        )
        if filters.institutions
        else "Todas las instituciones"
    )
    status_label = ", ".join(
        _STATUS_LABELS.get(s, s) for s in filters.effective_statuses
    )

    # Aggregates
    file_count = len(entries)
    total_bytes = sum(e.size_bytes for e in entries)
    vendor_count = len({e.vendor_id for e in entries})

    # Table rows
    rows_html = "".join(_render_entry_row(e) for e in entries)
    if not rows_html:
        rows_html = (
            '<tr><td colspan="8" class="empty">'
            "No hay documentos que cumplan los filtros aplicados. "
            "Revisa el rango de periodo, las instituciones seleccionadas "
            "o los estados incluidos."
            "</td></tr>"
        )

    document = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>{html.escape(title)}</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    font-family: "Helvetica Neue", Arial, sans-serif;
    color: #15233b;
    font-size: 11px;
    line-height: 1.45;
  }}
  body {{ padding: 8px 0; }}
  header {{
    border-bottom: 2px solid #0c2541;
    padding-bottom: 12px;
    margin-bottom: 18px;
  }}
  header .brand {{
    color: #0c2541;
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-weight: 600;
  }}
  header h1 {{
    margin: 6px 0 2px;
    font-size: 22px;
    color: #0c2541;
  }}
  header p.subtitle {{
    margin: 0;
    color: #4a5b78;
    font-size: 12px;
  }}
  .scope {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 24px;
    margin: 8px 0 18px;
    padding: 12px 14px;
    background: #f4f7fb;
    border: 1px solid #d8e2ef;
    border-radius: 6px;
  }}
  .scope dt {{
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #6b7a93;
    margin: 0;
  }}
  .scope dd {{
    margin: 2px 0 0;
    font-size: 12px;
    color: #15233b;
    font-weight: 500;
  }}
  .counters {{
    display: flex;
    gap: 18px;
    margin: 0 0 20px;
  }}
  .counter {{
    flex: 1;
    border: 1px solid #d8e2ef;
    border-radius: 6px;
    padding: 12px 14px;
    background: #fff;
  }}
  .counter strong {{
    display: block;
    font-size: 22px;
    color: #0c2541;
    margin: 4px 0 2px;
  }}
  .counter span {{
    color: #6b7a93;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  h2.section {{
    font-size: 13px;
    margin: 24px 0 8px;
    color: #0c2541;
    border-bottom: 1px solid #d8e2ef;
    padding-bottom: 4px;
  }}
  table.index {{
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
  }}
  table.index th, table.index td {{
    padding: 6px 8px;
    vertical-align: top;
    border-bottom: 1px solid #e3eaf3;
  }}
  table.index th {{
    text-align: left;
    background: #0c2541;
    color: #f4f7fb;
    font-size: 9px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-weight: 600;
  }}
  table.index tr:nth-child(even) td {{ background: #f8fafc; }}
  table.index td.empty {{
    text-align: center;
    color: #6b7a93;
    padding: 28px 12px;
    font-style: italic;
  }}
  table.index td.status {{ white-space: nowrap; }}
  table.index td.status.approved {{ color: #1b7a3b; font-weight: 600; }}
  table.index td.status.attention {{ color: #b25b0a; font-weight: 600; }}
  table.index td.status.rejected {{ color: #a02020; font-weight: 600; }}
  footer {{
    margin-top: 18px;
    border-top: 1px solid #d8e2ef;
    padding-top: 10px;
    color: #6b7a93;
    font-size: 9px;
    text-align: center;
  }}
  footer strong {{ color: #15233b; }}
</style>
</head>
<body>
  <header>
    <div class="brand">CheckWise · Plataforma de cumplimiento REPSE</div>
    <h1>Paquete para auditoría</h1>
    <p class="subtitle">{client_name} · RFC {client_rfc}</p>
  </header>

  <dl class="scope">
    <div>
      <dt>Periodo cubierto</dt>
      <dd>{html.escape(period_label)}</dd>
    </div>
    <div>
      <dt>Instituciones</dt>
      <dd>{html.escape(institution_label)}</dd>
    </div>
    <div>
      <dt>Estados incluidos</dt>
      <dd>{html.escape(status_label)}</dd>
    </div>
    <div>
      <dt>Generado</dt>
      <dd>{html.escape(generated_label)}</dd>
    </div>
  </dl>

  <div class="counters">
    <div class="counter">
      <span>Documentos</span>
      <strong>{file_count}</strong>
    </div>
    <div class="counter">
      <span>Proveedores</span>
      <strong>{vendor_count}</strong>
    </div>
    <div class="counter">
      <span>Tamaño</span>
      <strong>{_format_bytes(total_bytes)}</strong>
    </div>
  </div>

  <h2 class="section">Índice de documentos</h2>
  <table class="index">
    <thead>
      <tr>
        <th>Proveedor</th>
        <th>RFC</th>
        <th>Institución</th>
        <th>Periodo</th>
        <th>Requisito</th>
        <th>Estado</th>
        <th>Carga</th>
        <th>Archivo</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>

  <footer>
    Documento generado automáticamente por <strong>CheckWise</strong> ·
    Operado por Legal Shelf · México
  </footer>
</body>
</html>
"""
    return document.encode("utf-8")


def _render_entry_row(entry: AuditPackageEntry) -> str:
    status_label = _STATUS_LABELS.get(entry.status, entry.status)
    status_class = _status_tone(entry.status)
    submitted = entry.submitted_at_iso or ""
    if submitted:
        try:
            submitted = datetime.fromisoformat(submitted).strftime("%d/%m/%Y")
        except ValueError:
            submitted = entry.submitted_at_iso or ""
    institution_label = _INSTITUTION_LABELS.get(
        entry.institution_code, entry.institution_name or entry.institution_code
    )
    return (
        "<tr>"
        f"<td>{html.escape(entry.vendor_name)}</td>"
        f"<td>{html.escape(entry.vendor_rfc or '—')}</td>"
        f"<td>{html.escape(institution_label)}</td>"
        f"<td>{html.escape(entry.period_key)}</td>"
        f"<td>{html.escape(entry.requirement_name or entry.requirement_code or '—')}</td>"
        f'<td class="status {status_class}">{html.escape(status_label)}</td>'
        f"<td>{html.escape(submitted)}</td>"
        f"<td>{html.escape(entry.filename)}</td>"
        "</tr>"
    )


def _status_tone(status: str) -> str:
    if status in {"aprobado", "excepcion_legal"}:
        return "approved"
    if status in {"rechazado", "vencido"}:
        return "rejected"
    return "attention"


def _format_period_range(filters: AuditPackageFilters) -> str:
    if filters.period_from and filters.period_to:
        return f"{filters.period_from} a {filters.period_to}"
    if filters.period_from:
        return f"Desde {filters.period_from}"
    if filters.period_to:
        return f"Hasta {filters.period_to}"
    return "Sin restricción de periodo"


def _format_bytes(total: int) -> str:
    if total >= 1024 * 1024:
        return f"{total / (1024 * 1024):.1f} MB"
    if total >= 1024:
        return f"{total / 1024:.1f} KB"
    return f"{total} B"
