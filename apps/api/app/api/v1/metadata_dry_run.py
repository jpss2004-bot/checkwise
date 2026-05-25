"""Local metadata dry-run endpoints for n8n upload testing.

These endpoints are intentionally isolated from the production submission flow:
they do not write to the database, call AI, store files permanently, or approve
documents. Local OCR can be enabled explicitly for n8n prototyping. They only
combine an uploaded PDF with the real static metadata rulebook and return a
human-review payload.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.core.config import settings
from app.core.metadata_rules import UnknownDocumentTypeError
from app.core.security_gates import require_local_or_internal_admin
from tools.test_pdf_metadata_dry_run import build_pdf_metadata_dry_run_payload

# Trust boundary: this router is gated at the prefix. Anonymous in local
# only; outside local the caller must present an internal_admin JWT.
router = APIRouter(
    prefix="/metadata-dry-run",
    tags=["metadata-dry-run"],
    dependencies=[Depends(require_local_or_internal_admin)],
)


@router.post("/pdf")
async def create_pdf_metadata_dry_run(
    request: Request,
    file: Annotated[UploadFile, File()],
    document_type_code: Annotated[str, Form(min_length=1)],
    context_json: Annotated[str | None, Form()] = None,
    include_intelligence: Annotated[bool, Form()] = False,
    enable_ocr: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    """Build a metadata review payload for one uploaded PDF.

    This endpoint exists for local/n8n prototyping. It accepts multipart form
    uploads and delegates all rule/template behavior to the real backend
    rulebook through the existing local dry-run builder.
    """
    context = _parse_context_json(context_json)
    original_filename = Path(file.filename or "upload.pdf").name
    if not original_filename.lower().endswith(".pdf"):
        original_filename = f"{original_filename}.pdf"
    context.setdefault("uploaded_filename", original_filename)
    context.setdefault("upload_content_type", file.content_type)

    # Bound memory before reading the upload. If the client advertised a
    # Content-Length larger than MAX_UPLOAD_SIZE_BYTES, refuse immediately;
    # otherwise read with the same cap and reject mid-stream.
    max_bytes = settings.MAX_UPLOAD_SIZE_BYTES
    advertised = request.headers.get("content-length")
    if advertised and advertised.isdigit() and int(advertised) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo no puede pesar más de {max_bytes} bytes.",
        )
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo no puede pesar más de {max_bytes} bytes.",
        )
    if not content:
        raise HTTPException(
            status_code=422,
            detail="El PDF está vacío.",
        )

    with tempfile.TemporaryDirectory(prefix="checkwise-metadata-dry-run-") as temp_dir:
        pdf_path = Path(temp_dir) / original_filename
        pdf_path.write_bytes(content)
        try:
            return build_pdf_metadata_dry_run_payload(
                pdf_path=pdf_path,
                document_type_code=document_type_code,
                context=context,
                include_intelligence=include_intelligence,
                enable_ocr=enable_ocr,
            )
        except UnknownDocumentTypeError as exc:
            # Echo the offending code so the operator / n8n integration
            # sees which value was rejected. Field names like
            # ``document_type_code`` stay verbatim — they're API
            # contracts, not user-facing copy.
            raise HTTPException(
                status_code=422,
                detail=f"Tipo de documento desconocido: {document_type_code}.",
            ) from exc


def _parse_context_json(context_json: str | None) -> dict[str, Any]:
    if not context_json:
        return {}
    try:
        parsed = json.loads(context_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"El campo context_json debe ser JSON válido: {exc.msg}.",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=422,
            detail="El campo context_json debe ser un objeto JSON.",
        )
    return parsed
