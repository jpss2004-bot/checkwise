from __future__ import annotations

import re
import unicodedata
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.catalogs import (
    DOCUMENT_STATUSES,
    INSTITUTIONS,
    LOAD_TYPES,
    REQUIREMENT_EXAMPLES,
    VALIDATION_RULES,
)
from app.db.session import get_db
from app.models import (
    AuditLog,
    Client,
    Contract,
    Document,
    DocumentStatusHistory,
    Institution,
    Period,
    Requirement,
    RequirementVersion,
    Submission,
    Validation,
    Vendor,
)
from app.schemas.catalogs import CatalogResponse
from app.schemas.submissions import SubmissionResponse
from app.services.prevalidation import build_initial_validations
from app.services.storage import LocalStorageService

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
EvidenceFile = Annotated[UploadFile, File()]


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
    initial_status: Annotated[str, Form()] = "pendiente_revision",
    contract_reference: Annotated[str | None, Form()] = None,
) -> SubmissionResponse:
    if initial_status != "pendiente_revision":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La carga inicial debe comenzar en pendiente_revision.",
        )

    valid_statuses = {item["code"] for item in DOCUMENT_STATUSES}
    if initial_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Estado inválido."
        )

    valid_load_types = {item["code"] for item in LOAD_TYPES}
    if load_type not in valid_load_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tipo de carga inválido."
        )

    valid_institutions = {item["code"] for item in INSTITUTIONS}
    if institution_code not in valid_institutions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Institución inválida."
        )

    storage = LocalStorageService()
    try:
        stored_file = await storage.save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        duplicate = db.scalar(
            select(Document).where(Document.sha256 == stored_file.sha256).limit(1)
        )

        client = _get_or_create_client(db, client_name.strip())
        institution = _get_or_create_institution(db, institution_code)
        vendor = _get_or_create_vendor(
            db, client.id, vendor_name.strip(), vendor_rfc.upper().strip()
        )
        period = _get_or_create_period(db, period_code.strip(), load_type)
        requirement, requirement_version = _get_or_create_requirement(
            db,
            institution_id=institution.id,
            institution_code=institution.code,
            load_type=load_type,
            requirement_name=requirement_name.strip(),
        )
        contract = _get_or_create_contract(db, client.id, vendor.id, contract_reference)

        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            contract_id=contract.id if contract else None,
            period_id=period.id,
            institution_id=institution.id,
            requirement_id=requirement.id,
            requirement_version_id=requirement_version.id,
            load_type=load_type,
            source="portal",
            status=initial_status,
            comments=comments,
            submitted_by="local-form",
        )
        db.add(submission)
        db.flush()

        document = Document(
            submission_id=submission.id,
            storage_key=stored_file.storage_key,
            original_filename=stored_file.original_filename,
            mime_type=stored_file.mime_type,
            size_bytes=stored_file.size_bytes,
            sha256=stored_file.sha256,
            status=initial_status,
        )
        db.add(document)
        db.flush()

        signals = build_initial_validations(
            stored_file,
            duplicate_found=duplicate is not None,
            human_review_required=requirement_version.human_review_required,
        )
        for signal in signals:
            db.add(
                Validation(
                    submission_id=submission.id,
                    document_id=document.id,
                    rule_code=signal.rule_code,
                    rule_type=signal.rule_type,
                    result=signal.result,
                    severity=signal.severity,
                    message=signal.message,
                    requires_human_review=signal.requires_human_review,
                )
            )

        db.add(
            DocumentStatusHistory(
                document_id=document.id,
                submission_id=submission.id,
                from_status=None,
                to_status=initial_status,
                reason="Carga inicial desde portal local.",
                actor="system",
            )
        )
        db.add(
            AuditLog(
                action="submission.created",
                entity_type="submission",
                entity_id=submission.id,
                after={
                    "client_id": client.id,
                    "vendor_id": vendor.id,
                    "period_id": period.id,
                    "requirement_id": requirement.id,
                    "status": initial_status,
                },
                event_metadata={
                    "source": "portal",
                    "storage_key": stored_file.storage_key,
                    "sha256": stored_file.sha256,
                },
            )
        )

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible registrar la carga documental.",
        ) from exc

    return SubmissionResponse(
        submission_id=submission.id,
        document_id=document.id,
        status=initial_status,
        sha256=stored_file.sha256,
        storage_key=stored_file.storage_key,
        validations=signals,
        message="Carga recibida. El documento queda pendiente de revisión humana.",
    )


def _get_or_create_client(db: Session, name: str) -> Client:
    client = db.scalar(select(Client).where(Client.name == name).limit(1))
    if client:
        return client
    client = Client(name=name, status="active")
    db.add(client)
    db.flush()
    return client


def _get_or_create_vendor(db: Session, client_id: str, name: str, rfc: str) -> Vendor:
    vendor = db.scalar(
        select(Vendor).where(Vendor.client_id == client_id, Vendor.rfc == rfc).limit(1)
    )
    if vendor:
        if vendor.name != name:
            vendor.name = name
        return vendor
    vendor = Vendor(client_id=client_id, name=name, rfc=rfc, status="active")
    db.add(vendor)
    db.flush()
    return vendor


def _get_or_create_institution(db: Session, code: str) -> Institution:
    institution = db.scalar(select(Institution).where(Institution.code == code).limit(1))
    if institution:
        return institution
    label = next(item["label"] for item in INSTITUTIONS if item["code"] == code)
    institution = Institution(code=code, name=label)
    db.add(institution)
    db.flush()
    return institution


def _get_or_create_period(db: Session, code: str, period_type: str) -> Period:
    period = db.scalar(
        select(Period).where(Period.code == code, Period.period_type == period_type).limit(1)
    )
    if period:
        return period

    year, month = _parse_year_month(code)
    period = Period(code=code, year=year, month=month, period_type=period_type)
    db.add(period)
    db.flush()
    return period


def _get_or_create_requirement(
    db: Session,
    *,
    institution_id: str,
    institution_code: str,
    load_type: str,
    requirement_name: str,
) -> tuple[Requirement, RequirementVersion]:
    code = _requirement_code(institution_code, load_type, requirement_name)
    requirement = db.scalar(select(Requirement).where(Requirement.code == code).limit(1))
    if not requirement:
        requirement = Requirement(
            code=code,
            name=requirement_name,
            institution_id=institution_id,
            load_type=load_type,
            frequency=load_type,
            risk_level="alto",
            current_version=1,
        )
        db.add(requirement)
        db.flush()

    version = db.scalar(
        select(RequirementVersion)
        .where(
            RequirementVersion.requirement_id == requirement.id,
            RequirementVersion.version == requirement.current_version,
        )
        .limit(1)
    )
    if not version:
        version = RequirementVersion(
            requirement_id=requirement.id,
            version=requirement.current_version,
            legal_basis="Pendiente de semilla completa desde matriz regulatoria REPSE 2026.",
            applicability_rule="Aplica según cliente, proveedor, contrato, periodo e institución.",
            minimum_validation="Archivo legible, tipo permitido, hash calculado y revisión humana.",
            automatic_signals=(
                "archivo existe; tipo permitido; tamaño máximo; hash; duplicado por hash"
            ),
            human_review_required=True,
            missing_state="pendiente_revision",
            implementation_notes=(
                "Requisito creado desde carga inicial; debe reconciliarse con catálogo oficial."
            ),
        )
        db.add(version)
        db.flush()
    return requirement, version


def _get_or_create_contract(
    db: Session, client_id: str, vendor_id: str, external_reference: str | None
) -> Contract | None:
    if not external_reference:
        return None
    contract = db.scalar(
        select(Contract)
        .where(
            Contract.client_id == client_id,
            Contract.vendor_id == vendor_id,
            Contract.external_reference == external_reference,
        )
        .limit(1)
    )
    if contract:
        return contract
    contract = Contract(
        client_id=client_id,
        vendor_id=vendor_id,
        external_reference=external_reference,
        status="active",
    )
    db.add(contract)
    db.flush()
    return contract


def _parse_year_month(code: str) -> tuple[int | None, int | None]:
    match = re.search(r"(20\d{2})[-/ ]?(0?[1-9]|1[0-2])?", code)
    if not match:
        return None, None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else None
    return year, month


def _requirement_code(institution_code: str, load_type: str, name: str) -> str:
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").upper()
    slug = slug[:34] or "REQUISITO"
    return f"REQ-{institution_code.upper()}-{load_type.upper()}-{slug}"
