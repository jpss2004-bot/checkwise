"""Core API: health, catalogs, and the legacy native-intake submission endpoint.

The intake helpers (entity get-or-create, status derivation, validation
event timeline, requirement + period resolution) live in
``app.services.submission_service`` and ``app.services.requirement_service``.

``POST /api/v1/submissions`` here is the LEGACY native-intake endpoint. It
trusts browser-posted tenant identity (client / vendor / contract) so a
caller can spoof another company's row by changing the form fields. The
endpoint is preserved for the importer + dev workflows and existing test
coverage, NOT for production provider uploads. The tenant-safe replacement
lives at ``POST /api/v1/portal/workspaces/{workspace_id}/submissions`` —
identity is derived from the authenticated workspace there.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.core.catalogs import (
    DOCUMENT_STATUSES,
    INSTITUTIONS,
    LOAD_TYPES,
    REQUIREMENT_EXAMPLES,
    VALIDATION_RULES,
)
from app.core.security_gates import require_local_or_internal_admin
from app.db.session import get_db
from app.schemas.catalogs import CatalogResponse
from app.schemas.submissions import SubmissionResponse
from app.services.requirement_service import resolve_period, resolve_requirement
from app.services.storage import get_storage_service
from app.services.submission_service import (
    INTAKE_SOURCE_LEGACY_NATIVE,
    assert_pdf_upload,
    finalize_intake_submission,
    get_or_create_client,
    get_or_create_contract,
    get_or_create_institution,
    get_or_create_vendor,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
EvidenceFile = Annotated[UploadFile, File()]

VALID_DOCUMENT_STATUSES = frozenset(item["code"] for item in DOCUMENT_STATUSES)
VALID_LOAD_TYPES = frozenset(item["code"] for item in LOAD_TYPES)
VALID_INSTITUTION_CODES = frozenset(item["code"] for item in INSTITUTIONS)


@router.get("/health", tags=["system"])
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "checkwise-api"}


@router.get("/health/db", tags=["system"])
def db_health(db: DbSession) -> dict[str, str]:
    db.execute(text("select 1"))
    return {"status": "ok", "database": "reachable"}


@router.get("/catalogs", response_model=CatalogResponse, tags=["catalogs"])
def get_catalogs() -> CatalogResponse:
    return CatalogResponse(
        document_statuses=DOCUMENT_STATUSES,
        load_types=LOAD_TYPES,
        institutions=INSTITUTIONS,
        validation_rules=VALIDATION_RULES,
        requirement_examples=REQUIREMENT_EXAMPLES,
    )


@router.post(
    "/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["submissions"],
    deprecated=True,
    summary="Legacy native-intake submission (deprecated, gated)",
    description=(
        "DEPRECATED. Trusts browser-posted tenant identity (client / vendor / "
        "contract / RFC). Kept for the importer, dev workflows, and existing "
        "test coverage. For tenant-safe provider uploads use "
        "`POST /api/v1/portal/workspaces/{workspace_id}/submissions`, which "
        "derives tenant identity from the authenticated workspace. "
        "Outside `CHECKWISE_ENV=local` this endpoint requires the "
        "`internal_admin` role on a bearer JWT — it is never anonymous "
        "in production."
    ),
    # Trust boundary: anonymous in local only; internal_admin everywhere else.
    dependencies=[Depends(require_local_or_internal_admin)],
)
async def create_submission(
    client_name: Annotated[str, Form(min_length=2)],
    vendor_name: Annotated[str, Form(min_length=2)],
    vendor_rfc: Annotated[str, Form(min_length=12, max_length=13)],
    period_code: Annotated[str, Form(min_length=4)],
    load_type: Annotated[str, Form()],
    institution_code: Annotated[str, Form()],
    requirement_name: Annotated[str, Form(min_length=2)],
    file: EvidenceFile,
    db: DbSession,
    comments: Annotated[str | None, Form()] = None,
    initial_status: Annotated[str, Form()] = DocumentStatus.PENDIENTE_REVISION.value,
    contract_reference: Annotated[str | None, Form()] = None,
    # Canonical IDs introduced by the Reconciliation Patch. Both optional for
    # the deprecation window (one minor version): when provided, the canonical
    # path takes precedence over ``requirement_name`` / ``period_code`` and
    # the submission is bound to the catalog. When absent, the legacy free-
    # text path runs with a deprecation event recorded against the submission.
    requirement_code: Annotated[str | None, Form()] = None,
    period_key: Annotated[str | None, Form()] = None,
) -> SubmissionResponse:
    assert_pdf_upload(file)

    if initial_status != DocumentStatus.PENDIENTE_REVISION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La carga inicial debe comenzar en pendiente_revision.",
        )

    if initial_status not in VALID_DOCUMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Estado inválido."
        )

    if load_type not in VALID_LOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Tipo de carga inválido."
        )

    if institution_code not in VALID_INSTITUTION_CODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Institución inválida."
        )

    storage = get_storage_service()
    try:
        stored_file = await storage.save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        # LEGACY tenant identity path — browser-posted, not authoritative.
        # See module docstring; the workspace-scoped endpoint resolves these
        # from the authenticated ProviderWorkspace instead.
        client = get_or_create_client(db, client_name.strip())
        institution = get_or_create_institution(db, institution_code)
        vendor = get_or_create_vendor(
            db, client.id, vendor_name.strip(), vendor_rfc.upper().strip()
        )
        resolved_requirement = resolve_requirement(
            db,
            requirement_code=(requirement_code or "").strip() or None,
            requirement_name=requirement_name.strip(),
            institution_id=institution.id,
            institution_code=institution.code,
            load_type=load_type,
        )
        resolved_period = resolve_period(
            db,
            period_key=(period_key or "").strip() or None,
            period_code=period_code.strip(),
            load_type=load_type,
        )
        contract = get_or_create_contract(db, client.id, vendor.id, contract_reference)

        return finalize_intake_submission(
            db,
            stored_file=stored_file,
            client=client,
            vendor=vendor,
            contract=contract,
            institution=institution,
            resolved_requirement=resolved_requirement,
            resolved_period=resolved_period,
            load_type=load_type,
            period_code=period_code.strip(),
            comments=comments,
            submitted_by="local-form",
            intake_source=INTAKE_SOURCE_LEGACY_NATIVE,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible registrar la carga documental.",
        ) from exc
