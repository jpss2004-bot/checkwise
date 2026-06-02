"""Prep the 2026-06-01 user-testing synthetic tenant for online deployment.

This is the companion to:
  - scripts/sql/ut_2026_06_01_seed.sql      (static rows)
  - scripts/sql/ut_2026_06_01_teardown.sql  (off-switch)

It does the three things that pure SQL cannot:

  1. Computes bcrypt password hashes for the 5 synthetic users.
  2. Generates synthetic PDFs (reportlab) and uploads them to the
     configured object store (R2/S3 in production, LocalStorageService
     when CHECKWISE_ENV=local).
  3. Emits scripts/sql/ut_2026_06_01_submissions.generated.sql with all
     submission / document / inspection / status-history / validation
     INSERTs, referencing the deterministic UUIDs already committed by
     the static seed.

USAGE
-----

  # Step 1 — generate bcrypt hashes only (safe to run anywhere):
  python scripts/ut_2026_06_01_prep.py --hashes-only

  # Step 2 — dry-run that does NOT touch storage and does NOT write
  # the generated SQL file (useful to preview what would happen):
  python scripts/ut_2026_06_01_prep.py --dry-run

  # Step 3 — full prep. Generates PDFs, uploads to storage, writes the
  # generated submissions SQL. Refuses to run against a non-local
  # environment unless --confirm-prod is also passed.
  python scripts/ut_2026_06_01_prep.py --apply
  python scripts/ut_2026_06_01_prep.py --apply --confirm-prod

  # Optional — delete every R2 object under user-testing/2026-06-01/ .
  # Pairs with the SQL teardown. Refuses prod without --confirm-prod.
  python scripts/ut_2026_06_01_prep.py --teardown-storage

OUTPUTS
-------
  ./out/ut_2026_06_01_hashes.env                          (gitignored)
  scripts/sql/ut_2026_06_01_submissions.generated.sql     (gitignored)

INVARIANTS
----------
  * Never touches any row that is not part of the synthetic scenario.
  * Re-runnable. Reusing the same hashes file across runs keeps the
    seed.sql ON CONFLICT DO UPDATE behaviour deterministic.
  * Never destructive against the database. All DB changes happen via
    psql against the generated SQL files — this script only writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable

# Make ``app`` importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt  # noqa: E402
from reportlab.lib.colors import HexColor, black  # noqa: E402
from reportlab.lib.pagesizes import LETTER  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app.constants.statuses import DocumentStatus  # noqa: E402
from app.core.compliance_catalog import recurring_for_year  # noqa: E402
from app.core.config import settings  # noqa: E402

# ============================================================================
# CONSTANTS — must stay in lockstep with seed.sql and teardown.sql
# ============================================================================

SCENARIO_TAG = "user_testing_2026_06_01"
SCENARIO_NAMESPACE = uuid.UUID("03b62ad7-b7f2-4f9f-bc04-260601000001")

CLIENT_ID = "496da43d-8125-532a-8a28-a8ba460c5587"
ANWAR_USER_ID = "1a6fb3b5-efb9-5540-9190-bebe07e2280e"

USERS = [
    # (env_var_name,    plaintext_password,       full_name)
    ("MAYELA_HASH",     "MayelaLocal!2026",       "Mayela"),
    ("ANWAR_HASH",      "AnwarLocal!2026",        "Anwar"),
    ("ALFA_HASH",       "ProviderAlfa!2026",      "Operaciones Alfa"),
    ("MINA_HASH",       "MinaLocal!2026",         "Mina Olaez"),
    ("COBRE_HASH",      "ProviderCobre!2026",     "Operaciones Cobre"),
]


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    vendor_id: str
    vendor_name: str
    vendor_rfc: str
    owner_name: str
    scenario_note: str


PROVIDERS = [
    Provider(
        key="provider-a",
        label="Provider A — high compliance",
        vendor_id="a7b16b60-3afc-5d0e-8c7f-6791d4324269",
        vendor_name="Servicios Alfa Sintéticos · Local",
        vendor_rfc="SAS260601AA1",
        owner_name="Operaciones Alfa",
        scenario_note="Mostly complete and healthy portfolio state.",
    ),
    Provider(
        key="provider-b",
        label="Provider B — partial compliance",
        vendor_id="75c7e481-7b6e-5a38-8637-c7d25b6ec47d",
        vendor_name="Servicios Beta Sintéticos · Local",
        vendor_rfc="SBS260601BB2",
        owner_name="Mina Olaez",
        scenario_note="Partial compliance with pending and mismatch cases.",
    ),
    Provider(
        key="provider-c",
        label="Provider C — problematic compliance",
        vendor_id="45f593b3-6711-5240-a82c-4dcc614b79ad",
        vendor_name="Servicios Cobre Sintéticos · Local",
        vendor_rfc="SCS260601CC3",
        owner_name="Operaciones Cobre",
        scenario_note="Problematic provider with rejected, expired, and clarification states.",
    ),
]
PROVIDERS_BY_KEY = {p.key: p for p in PROVIDERS}


@dataclass(frozen=True)
class Submission:
    provider_key: str
    requirement_code: str
    status: str
    days_ago: int
    period_key: str | None
    reviewer_note: str | None = None


ONBOARDING_CODES = [
    "ONB-CONT-001",
    "ONB-CORP-M-001",
    "ONB-CORP-M-002",
    "ONB-REPSE-001",
    "ONB-PATR-001",
]

# Mirrors the explicit Provider B / Provider C scenarios from
# seed_user_testing_scenario.py. Provider A's full recurring catalog is
# materialised dynamically from recurring_for_year(2026, "moral").
EXPLICIT_RECURRING: list[Submission] = [
    # Provider B
    Submission("provider-b", "REC-SAT-2026-04-declaracion-iva",                          DocumentStatus.APROBADO.value,           9,  "2026-M04", "Documento sintetico aprobado."),
    Submission("provider-b", "REC-IMSS-2026-04-comprobante-de-pago-bancario",            DocumentStatus.PENDIENTE_REVISION.value, 5,  "2026-M04"),
    Submission("provider-b", "REC-INFONAVIT-2026-03-comprobante-de-pago-bancario",       DocumentStatus.PENDIENTE_REVISION.value, 3,  "2026-M03"),
    Submission("provider-b", "REC-ACUSES-2026-05-acuse-sisub",                           DocumentStatus.PENDIENTE_REVISION.value, 2,  "2026-M05"),
    # Provider C
    Submission("provider-c", "REC-SAT-2026-03-declaracion-iva",                          DocumentStatus.RECHAZADO.value,         20,  "2026-M03",
               "La declaracion sintetica trae periodo incorrecto. Requiere sustitucion."),
    Submission("provider-c", "REC-SAT-2026-04-comprobantes-de-nomina-de-los-trabajadores", DocumentStatus.REQUIERE_ACLARACION.value, 14, "2026-M04",
               "Falta un comprobante de nomina sintetico en el paquete."),
    Submission("provider-c", "REC-IMSS-2026-03-comprobante-de-pago-bancario",            DocumentStatus.VENCIDO.value,           45,  "2026-M03"),
    Submission("provider-c", "REC-INFONAVIT-2026-03-comprobante-de-pago-bancario",       DocumentStatus.POSIBLE_MISMATCH.value,  13,  "2026-M03"),
    Submission("provider-c", "REC-ACUSES-2026-05-acuse-icsoe",                           DocumentStatus.RECHAZADO.value,         11,  "2026-M05",
               "El acuse ICSOE sintetico esta incompleto; falta pagina de confirmacion."),
]

ONBOARDING_SUBMISSIONS: list[Submission] = []
for code in ONBOARDING_CODES:
    ONBOARDING_SUBMISSIONS.append(Submission("provider-a", code, DocumentStatus.APROBADO.value, 22, None, "Validado en escenario sintetico."))
    ONBOARDING_SUBMISSIONS.append(Submission("provider-b", code, DocumentStatus.APROBADO.value, 18, None, "Validado en escenario sintetico."))
ONBOARDING_SUBMISSIONS.extend([
    Submission("provider-c", "ONB-CONT-001",  DocumentStatus.APROBADO.value,            25, None, "Contrato sintetico validado."),
    Submission("provider-c", "ONB-REPSE-001", DocumentStatus.RECHAZADO.value,           12, None, "El folio REPSE sintetico no corresponde al periodo indicado. Solicitar nuevo documento."),
    Submission("provider-c", "ONB-PATR-001",  DocumentStatus.REQUIERE_ACLARACION.value, 10, None, "Falta constancia sintetica de registro patronal. El proveedor debe aclarar."),
])


def all_submissions() -> list[Submission]:
    """Onboarding + Provider A green catalog + explicit B/C scenarios."""
    out = list(ONBOARDING_SUBMISSIONS)
    for item in recurring_for_year(2026, "moral"):
        out.append(
            Submission(
                provider_key="provider-a",
                requirement_code=item.code,
                status=DocumentStatus.APROBADO.value,
                days_ago=8,
                period_key=item.period_key,
                reviewer_note="Documento sintetico aprobado.",
            )
        )
    out.extend(EXPLICIT_RECURRING)
    return out


# ============================================================================
# DETERMINISTIC IDs (uuid5 — must match seeder's _id() function)
# ============================================================================

def _uuid(seed: str) -> str:
    return str(uuid.uuid5(SCENARIO_NAMESPACE, seed))


def submission_id(s: Submission) -> str:
    return _uuid(f"{s.provider_key}:{s.requirement_code}:{s.period_key or 'onboarding'}")


def document_id(s: Submission) -> str:
    return _uuid(f"document:{s.provider_key}:{s.requirement_code}:{s.period_key or 'onboarding'}")


def inspection_id(s: Submission) -> str:
    return _uuid(f"inspection:{s.provider_key}:{s.requirement_code}:{s.period_key or 'onboarding'}")


def history_received_id(s: Submission) -> str:
    return _uuid(f"history:received:{s.provider_key}:{s.requirement_code}:{s.period_key or 'onboarding'}")


def history_state_id(s: Submission) -> str:
    return _uuid(f"history:state:{s.provider_key}:{s.requirement_code}:{s.period_key or 'onboarding'}")


def validation_id(s: Submission) -> str:
    return _uuid(f"validation:{s.provider_key}:{s.requirement_code}:{s.period_key or 'onboarding'}")


def review_event_id(s: Submission) -> str:
    return _uuid(f"review:{s.provider_key}:{s.requirement_code}:{s.period_key or 'onboarding'}")


def mismatch_event_id(s: Submission) -> str:
    return _uuid(f"mismatch:{s.provider_key}:{s.requirement_code}:{s.period_key or 'onboarding'}")


def period_id_for(period_key: str | None) -> str:
    """Returns the deterministic UUID for a period; matches the period rows
    seeded by seed.sql for the well-known keys."""
    if period_key is None:
        return _uuid("period:alta-inicial")
    return _uuid(f"period:{period_key}")


# ============================================================================
# PDF generation
# ============================================================================

def render_synthetic_pdf(
    *,
    title: str,
    provider: Provider,
    requirement_code: str,
    period_key: str | None,
    status_value: str,
    reviewer_note: str | None,
) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    c.setFillColor(HexColor("#ECFEFF"))
    c.rect(0, height - 66, width, 66, fill=1, stroke=0)
    c.setFillColor(HexColor("#013557"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, height - 38, "DOCUMENTO SINTETICO · CHECKWISE USER TEST")

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 21)
    c.drawString(72, height - 120, title[:80])
    c.setFont("Helvetica", 10)
    c.drawString(72, height - 146, "Uso: escenario de pruebas de usuario. Sin validez fiscal, laboral ni legal.")

    rows = [
        ("Proveedor", provider.vendor_name),
        ("RFC sintetico", provider.vendor_rfc),
        ("Requisito", requirement_code),
        ("Periodo", period_key or "alta-inicial"),
        ("Estado esperado", status_value),
        ("Escenario", provider.scenario_note),
    ]
    y = height - 190
    for key, value in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, y, f"{key}:")
        c.setFont("Helvetica", 10)
        c.drawString(180, y, value)
        y -= 18

    body = [
        "Este PDF fue generado automaticamente para probar CheckWise sin exponer",
        "documentos reales, datos personales, informacion fiscal, nomina o folios",
        "de proveedores reales.",
        "",
        "Cualquier parecido con una constancia, acuse, pago, declaracion o",
        "liquidacion real es intencional solo a nivel de categoria documental.",
        "Los datos, importes, identificadores y fechas son ficticios.",
    ]
    if reviewer_note:
        body.extend(["", f"Nota de revisor sintetica: {reviewer_note}"])

    text = c.beginText(72, y - 18)
    text.setFont("Helvetica", 10)
    text.setLeading(15)
    for line in body:
        text.textLine(line)
    c.drawText(text)

    c.setFillColor(HexColor("#B91C1C"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width / 2, 52, "NO SUBIR A PRODUCCION · NO USAR COMO EVIDENCIA REAL")
    c.showPage()
    c.save()
    return buffer.getvalue()


def storage_key_for(s: Submission) -> str:
    safe_period = (s.period_key or "alta-inicial").replace("/", "-")
    safe_req = s.requirement_code.lower().replace("_", "-")
    return f"user-testing/2026-06-01/{s.provider_key}/{safe_period}/{safe_req}.pdf"


# ============================================================================
# STORAGE — local vs S3/R2
# ============================================================================

def _get_storage_backend():
    """Returns an object with .save_bytes(storage_key=..., data=..., content_type=...) and .delete()."""
    if settings.is_local_env:
        from app.services.storage import LocalStorageService

        return LocalStorageService()
    from app.services.storage import S3StorageService

    return S3StorageService()


# ============================================================================
# SQL emission helpers
# ============================================================================

def _sql_str(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _sql_json(payload: dict | list | None) -> str:
    if payload is None:
        return "NULL"
    return _sql_str(json.dumps(payload, ensure_ascii=False, sort_keys=True)) + "::jsonb"


def _interval(days: int) -> str:
    # Use minutes precision so order of inserts feels realistic in audit views.
    return f"(NOW() - INTERVAL '{days} days')"


def _interval_offset(days: int, plus_minutes: int) -> str:
    return f"(NOW() - INTERVAL '{days} days' + INTERVAL '{plus_minutes} minutes')"


def _interval_offset_hours(days: int, plus_hours: int) -> str:
    return f"(NOW() - INTERVAL '{days} days' + INTERVAL '{plus_hours} hours')"


def _reviewer_action(status_value: str, explicit: str | None) -> tuple[str | None, str | None]:
    if not explicit:
        return None, explicit
    mapping = {
        DocumentStatus.RECHAZADO.value: "reject",
        DocumentStatus.REQUIERE_ACLARACION.value: "request_clarification",
        DocumentStatus.EXCEPCION_LEGAL.value: "mark_exception",
        DocumentStatus.APROBADO.value: "approve",
    }
    return mapping.get(status_value), explicit


HUMAN_REVIEW_STATUSES = {
    DocumentStatus.PENDIENTE_REVISION.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
    DocumentStatus.REQUIERE_ACLARACION.value,
    DocumentStatus.RECHAZADO.value,
}


# ============================================================================
# SQL FRAGMENT GENERATION (one block per submission)
# ============================================================================

def emit_period_inserts(submissions: list[Submission]) -> list[str]:
    """Emit any period rows for keys not already in seed.sql."""
    seeded = {None, "2026-M03", "2026-M04", "2026-M05"}
    seen: set[str] = set()
    out: list[str] = []
    for s in submissions:
        if s.period_key in seeded or s.period_key in seen:
            continue
        seen.add(s.period_key)
        year_str = s.period_key[:4] if (s.period_key and s.period_key[:4].isdigit()) else "NULL"
        month_str = "NULL"
        if s.period_key and "-M" in s.period_key:
            try:
                month_str = str(int(s.period_key.split("-M", 1)[1]))
            except ValueError:
                month_str = "NULL"
        out.append(
            "INSERT INTO periods (id, code, period_key, year, month, period_type, created_at, updated_at) VALUES "
            f"({_sql_str(period_id_for(s.period_key))}, "
            f"{_sql_str(f'{SCENARIO_TAG}-{s.period_key}')}, "
            f"{_sql_str(s.period_key)}, "
            f"{year_str}, {month_str}, "
            f"{_sql_str('mensual' if (s.period_key and '-M' in s.period_key) else 'anual')}, "
            f"NOW(), NOW()) ON CONFLICT (code, period_type) DO NOTHING;"
        )
    return out


def emit_submission_block(s: Submission, *, sha256: str, size_bytes: int, dry_run: bool) -> str:
    """Emit the full row graph for one submission. Returns SQL text."""
    provider = PROVIDERS_BY_KEY[s.provider_key]
    sub_id = submission_id(s)
    doc_id = document_id(s)
    insp_id = inspection_id(s)
    val_id = validation_id(s)
    history_recv = history_received_id(s)
    history_state = history_state_id(s)
    s_storage_key = storage_key_for(s)
    s_period_id = period_id_for(s.period_key)
    requires_review = s.status in HUMAN_REVIEW_STATUSES
    confidence = 0.92 if s.status in {DocumentStatus.APROBADO.value, DocumentStatus.PREVALIDADO.value} else 0.61
    mismatch_reason = (
        "RFC sintetico no coincide con el proveedor esperado."
        if s.status == DocumentStatus.POSIBLE_MISMATCH.value
        else None
    )
    validation_result = "warning" if s.status == DocumentStatus.POSIBLE_MISMATCH.value else "pass"
    validation_severity = "warning" if s.status == DocumentStatus.POSIBLE_MISMATCH.value else "info"
    filename = f"{s.provider_key}-{s.requirement_code.lower()}-{s.period_key or 'alta'}.pdf"

    submitted_at = _interval(s.days_ago)
    history_state_at = _interval_offset(s.days_ago, plus_minutes=5)

    lines: list[str] = []
    lines.append(f"-- ========== {provider.label} | {s.requirement_code} | {s.period_key or 'alta-inicial'} | {s.status} ==========")

    # SUBMISSION (FK lookups against the live catalog)
    lines.append(
        "INSERT INTO submissions ("
        " id, client_id, vendor_id, period_id, institution_id, requirement_id, requirement_version_id,"
        " load_type, source, status, requirement_code, period_key, comments, submitted_by, created_at, updated_at"
        ") SELECT "
        f"{_sql_str(sub_id)}, "
        f"{_sql_str(CLIENT_ID)}, "
        f"{_sql_str(provider.vendor_id)}, "
        f"{_sql_str(s_period_id)}, "
        "r.institution_id, "
        "r.id, "
        "(SELECT rv.id FROM requirement_versions rv WHERE rv.requirement_id = r.id ORDER BY rv.version ASC LIMIT 1), "
        "r.frequency, "
        "'portal', "
        f"{_sql_str(s.status)}, "
        f"{_sql_str(s.requirement_code)}, "
        f"{_sql_str(s.period_key)}, "
        f"{_sql_str(f'{SCENARIO_TAG}: {provider.label}')}, "
        f"{_sql_str(provider.owner_name)}, "
        f"{submitted_at}, {submitted_at} "
        f"FROM requirements r WHERE r.code = {_sql_str(s.requirement_code)} "
        "ON CONFLICT (id) DO NOTHING;"
    )

    # DOCUMENT
    lines.append(
        "INSERT INTO documents ("
        " id, submission_id, storage_key, original_filename, mime_type, size_bytes, sha256,"
        " status, ocr_status, created_at, updated_at"
        ") VALUES ("
        f"{_sql_str(doc_id)}, "
        f"{_sql_str(sub_id)}, "
        f"{_sql_str(s_storage_key)}, "
        f"{_sql_str(filename)}, "
        "'application/pdf', "
        f"{size_bytes}, "
        f"{_sql_str(sha256)}, "
        f"{_sql_str(s.status)}, "
        "'not_started', "
        f"{submitted_at}, {submitted_at}"
        ") ON CONFLICT (id) DO NOTHING;"
    )

    # INSPECTION (FK lookups against catalog for detected_institution and detected_document_type)
    detected_dates = json.dumps([(datetime.now(timezone.utc) - timedelta(days=s.days_ago)).date().isoformat()])
    detected_rfcs = json.dumps([provider.vendor_rfc])
    period_mentions = json.dumps([s.period_key] if s.period_key else [])
    lines.append(
        "INSERT INTO document_inspections ("
        " id, document_id, is_pdf, is_corrupt, is_encrypted, page_count, text_char_count, has_text,"
        " is_probably_scanned, detected_institution, detected_document_type, detected_rfcs,"
        " detected_dates, period_mentions, requirement_match_confidence, mismatch_reason,"
        " raw_metadata, created_at, updated_at"
        ") SELECT "
        f"{_sql_str(insp_id)}, "
        f"{_sql_str(doc_id)}, "
        "true, false, false, 1, 1200, true, false, "
        "(SELECT i.code FROM institutions i WHERE i.id = r.institution_id), "
        "r.name, "
        f"{_sql_str(detected_rfcs)}::jsonb, "
        f"{_sql_str(detected_dates)}::jsonb, "
        f"{_sql_str(period_mentions)}::jsonb, "
        f"{confidence}, "
        f"{_sql_str(mismatch_reason)}, "
        f"{_sql_json({'scenario': SCENARIO_TAG, 'synthetic': True})}, "
        f"{submitted_at}, {submitted_at} "
        f"FROM requirements r WHERE r.code = {_sql_str(s.requirement_code)} "
        "ON CONFLICT (id) DO NOTHING;"
    )

    # STATUS HISTORY — always "received"
    lines.append(
        "INSERT INTO document_status_history ("
        " id, submission_id, document_id, from_status, to_status, reason, actor, created_at"
        ") VALUES ("
        f"{_sql_str(history_recv)}, "
        f"{_sql_str(sub_id)}, "
        f"{_sql_str(doc_id)}, "
        "NULL, "
        f"{_sql_str(DocumentStatus.RECIBIDO.value)}, "
        "'Documento sintetico recibido para prueba.', "
        f"{_sql_str(f'provider:{provider.owner_name}')}, "
        f"{submitted_at}"
        ") ON CONFLICT (id) DO NOTHING;"
    )

    # STATUS HISTORY — terminal state (only if not still RECIBIDO)
    if s.status != DocumentStatus.RECIBIDO.value:
        lines.append(
            "INSERT INTO document_status_history ("
            " id, submission_id, document_id, from_status, to_status, reason, actor, created_at"
            ") VALUES ("
            f"{_sql_str(history_state)}, "
            f"{_sql_str(sub_id)}, "
            f"{_sql_str(doc_id)}, "
            f"{_sql_str(DocumentStatus.RECIBIDO.value)}, "
            f"{_sql_str(s.status)}, "
            f"{_sql_str(s.reviewer_note)}, "
            "'system:user_testing_seed', "
            f"{history_state_at}"
            ") ON CONFLICT (id) DO NOTHING;"
        )

    # VALIDATION
    lines.append(
        "INSERT INTO validations ("
        " id, submission_id, document_id, rule_code, rule_type, result, severity, message,"
        " requires_human_review, created_at, updated_at"
        ") VALUES ("
        f"{_sql_str(val_id)}, "
        f"{_sql_str(sub_id)}, "
        f"{_sql_str(doc_id)}, "
        "'synthetic_fixture', 'user_testing_seed', "
        f"{_sql_str(validation_result)}, "
        f"{_sql_str(validation_severity)}, "
        "'Fixture sintetico generado; no contiene datos reales.', "
        f"{'true' if requires_review else 'false'}, "
        f"{submitted_at}, {submitted_at}"
        ") ON CONFLICT (id) DO NOTHING;"
    )

    # VALIDATION EVENT (conditional)
    action, note = _reviewer_action(s.status, s.reviewer_note)
    if action and note:
        review_at = _interval_offset_hours(s.days_ago, plus_hours=2)
        lines.append(
            "INSERT INTO validation_events ("
            " id, submission_id, document_id, event_type, rule_code, result, severity, message,"
            " confidence, payload, actor_type, created_at"
            ") VALUES ("
            f"{_sql_str(review_event_id(s))}, "
            f"{_sql_str(sub_id)}, "
            f"{_sql_str(doc_id)}, "
            "'reviewer_decision', 'reviewer_decision', "
            f"{_sql_str(action)}, "
            f"{_sql_str('info' if action == 'approve' else 'warning')}, "
            f"{_sql_str(note)}, "
            "NULL, "
            f"{_sql_json({'scenario': SCENARIO_TAG, 'synthetic': True, 'from_status': DocumentStatus.PENDIENTE_REVISION.value, 'to_status': s.status})}, "
            "'reviewer', "
            f"{review_at}"
            ") ON CONFLICT (id) DO NOTHING;"
        )
    elif s.status == DocumentStatus.POSIBLE_MISMATCH.value:
        mismatch_at = _interval_offset(s.days_ago, plus_minutes=6)
        lines.append(
            "INSERT INTO validation_events ("
            " id, submission_id, document_id, event_type, rule_code, result, severity, message,"
            " confidence, payload, actor_type, created_at"
            ") VALUES ("
            f"{_sql_str(mismatch_event_id(s))}, "
            f"{_sql_str(sub_id)}, "
            f"{_sql_str(doc_id)}, "
            "'prevalidation', 'synthetic_mismatch', "
            "'warning', 'warning', "
            f"{_sql_str(s.reviewer_note or 'Posible mismatch sintetico: revisar RFC y periodo.')}, "
            "0.61, "
            f"{_sql_json({'scenario': SCENARIO_TAG, 'synthetic': True})}, "
            "'system', "
            f"{mismatch_at}"
            ") ON CONFLICT (id) DO NOTHING;"
        )

    return "\n".join(lines)


# ============================================================================
# ORCHESTRATION
# ============================================================================

def write_hashes_env(out_path: Path) -> dict[str, str]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rounds = settings.AUTH_BCRYPT_ROUNDS
    hashes: dict[str, str] = {}
    for env_name, plaintext, _full_name in USERS:
        salt = bcrypt.gensalt(rounds=rounds)
        hashed = bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")
        hashes[env_name] = hashed
    lines = [
        "# Generated by ut_2026_06_01_prep.py — DO NOT COMMIT.",
        f"# Bcrypt rounds: {rounds}",
        "# Source this file or pass each var to psql -v before running",
        "# scripts/sql/ut_2026_06_01_seed.sql.",
        "",
    ]
    for env_name, hashed in hashes.items():
        # Shell-safe quoting: bcrypt strings contain $ which would expand in
        # double-quoted shell. Use single quotes.
        lines.append(f"{env_name}='{hashed}'")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {out_path}")
    return hashes


def upload_pdfs(submissions: list[Submission], *, dry_run: bool) -> dict[str, tuple[str, int]]:
    """Returns {submission_id: (sha256, size_bytes)} after (optionally) uploading."""
    backend = None if dry_run else _get_storage_backend()
    out: dict[str, tuple[str, int]] = {}
    for s in submissions:
        provider = PROVIDERS_BY_KEY[s.provider_key]
        # Title is the requirement code — prep.py does not look up the
        # human name from the DB. Keeps the prep step DB-free for the
        # storage path (the SQL emit step resolves names via subselects).
        pdf_bytes = render_synthetic_pdf(
            title=s.requirement_code,
            provider=provider,
            requirement_code=s.requirement_code,
            period_key=s.period_key,
            status_value=s.status,
            reviewer_note=s.reviewer_note,
        )
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        size = len(pdf_bytes)
        out[submission_id(s)] = (digest, size)
        if dry_run:
            continue
        backend.save_bytes(
            storage_key=storage_key_for(s),
            data=pdf_bytes,
            content_type="application/pdf",
        )
    return out


def emit_submissions_sql(submissions: list[Submission], hashes_index: dict[str, tuple[str, int]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = [
        "-- ============================================================================",
        f"-- ut_2026_06_01_submissions.generated.sql  ({len(submissions)} submissions)",
        "-- ============================================================================",
        "-- Generated by scripts/ut_2026_06_01_prep.py. Do not edit by hand.",
        "-- Run AFTER scripts/sql/ut_2026_06_01_seed.sql .",
        "-- ============================================================================",
        "",
        "\\set ON_ERROR_STOP on",
        "",
        "BEGIN;",
        "",
        "-- Period rows for keys not already in the static seed.sql.",
    ]
    period_inserts = emit_period_inserts(submissions)
    if period_inserts:
        blocks.extend(period_inserts)
    else:
        blocks.append("-- (no additional periods needed)")
    blocks.append("")

    for s in submissions:
        digest, size = hashes_index[submission_id(s)]
        blocks.append(emit_submission_block(s, sha256=digest, size_bytes=size, dry_run=False))
        blocks.append("")

    blocks.append("COMMIT;")
    blocks.append("")
    blocks.append("\\echo 'submissions seed complete.'")
    blocks.append("SELECT COUNT(*) AS synthetic_submissions FROM submissions WHERE comments LIKE '%user_testing_2026_06_01%';")
    blocks.append("SELECT COUNT(*) AS synthetic_documents   FROM documents   WHERE storage_key LIKE 'user-testing/2026-06-01/%';")
    out_path.write_text("\n".join(blocks), encoding="utf-8")
    print(f"  wrote {out_path}")


def teardown_storage(*, confirm_prod: bool) -> None:
    if not settings.is_local_env and not confirm_prod:
        raise SystemExit(
            "Refusing to delete storage objects in non-local env without --confirm-prod."
        )
    backend = _get_storage_backend()
    # Walk every potential submission and delete by storage_key. We rely on
    # the deterministic key construction; nothing else in the bucket should
    # match this prefix.
    deleted = 0
    for s in all_submissions():
        try:
            backend.delete(storage_key_for(s))
            deleted += 1
        except Exception as exc:  # noqa: BLE001 — best-effort
            print(f"  WARN: delete failed for {storage_key_for(s)}: {exc}")
    print(f"  deleted {deleted} storage objects under user-testing/2026-06-01/")


def assert_env_safe(*, confirm_prod: bool) -> None:
    env = settings.CHECKWISE_ENV
    if settings.is_local_env:
        return
    if not confirm_prod:
        raise SystemExit(
            f"CHECKWISE_ENV={env!r}. Refusing to upload PDFs or write generated SQL "
            "without --confirm-prod. Re-run with --confirm-prod once you have "
            "verified the synthetic tenant is appropriate for this environment."
        )


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Prep the 2026-06-01 user-testing scenario.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hashes-only", action="store_true",
                      help="Only compute bcrypt hashes. Safe to run anywhere.")
    mode.add_argument("--dry-run", action="store_true",
                      help="Run full pipeline locally (PDF render, ID compute) without uploading or writing SQL.")
    mode.add_argument("--apply", action="store_true",
                      help="Full prep: hashes, PDF upload, write submissions SQL.")
    mode.add_argument("--teardown-storage", action="store_true",
                      help="Delete every R2/local object under user-testing/2026-06-01/.")
    parser.add_argument("--confirm-prod", action="store_true",
                        help="Required to touch storage when CHECKWISE_ENV != 'local'.")
    parser.add_argument("--out-dir", default="out", help="Where to write generated files.")
    args = parser.parse_args()

    repo_api = Path(__file__).resolve().parent.parent
    out_dir = (repo_api / args.out_dir).resolve()
    sql_dir = (repo_api / "scripts" / "sql").resolve()

    print(f"CHECKWISE_ENV={settings.CHECKWISE_ENV}")
    print(f"STORAGE_BUCKET={settings.STORAGE_BUCKET}")

    if args.teardown_storage:
        teardown_storage(confirm_prod=args.confirm_prod)
        return

    if args.hashes_only:
        write_hashes_env(out_dir / "ut_2026_06_01_hashes.env")
        print("done. next: source the env file and run psql against seed.sql.")
        return

    submissions = all_submissions()
    print(f"Planning {len(submissions)} synthetic submissions across {len(PROVIDERS)} providers.")

    if args.dry_run:
        index = upload_pdfs(submissions, dry_run=True)
        emit_submissions_sql(submissions, index, sql_dir / "ut_2026_06_01_submissions.generated.sql.dryrun")
        print("dry-run done. inspect the .dryrun file; nothing was uploaded.")
        return

    # --apply path from here.
    assert_env_safe(confirm_prod=args.confirm_prod)
    write_hashes_env(out_dir / "ut_2026_06_01_hashes.env")
    print(f"Uploading PDFs to bucket={settings.STORAGE_BUCKET}…")
    index = upload_pdfs(submissions, dry_run=False)
    emit_submissions_sql(submissions, index, sql_dir / "ut_2026_06_01_submissions.generated.sql")
    print("")
    print("apply complete. next steps:")
    print(f"  set -a; source {out_dir / 'ut_2026_06_01_hashes.env'}; set +a")
    print("  psql \"$DATABASE_URL\" \\")
    print("    -v mayela_hash=\"$MAYELA_HASH\" -v anwar_hash=\"$ANWAR_HASH\" \\")
    print("    -v alfa_hash=\"$ALFA_HASH\"   -v mina_hash=\"$MINA_HASH\"   -v cobre_hash=\"$COBRE_HASH\" \\")
    print("    -f scripts/sql/ut_2026_06_01_seed.sql")
    print("  psql \"$DATABASE_URL\" -f scripts/sql/ut_2026_06_01_submissions.generated.sql")


if __name__ == "__main__":
    main()
