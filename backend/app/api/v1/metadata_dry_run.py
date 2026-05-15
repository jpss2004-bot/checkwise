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

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.metadata_rules import UnknownDocumentTypeError
from tools.test_pdf_metadata_dry_run import build_pdf_metadata_dry_run_payload

router = APIRouter(prefix="/metadata-dry-run", tags=["metadata-dry-run"])


@router.post("/pdf")
async def create_pdf_metadata_dry_run(
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

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=422,
            detail="Uploaded PDF is empty.",
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
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc


def _parse_context_json(context_json: str | None) -> dict[str, Any]:
    if not context_json:
        return {}
    try:
        parsed = json.loads(context_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"context_json must be valid JSON: {exc.msg}",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=422,
            detail="context_json must be a JSON object.",
        )
    return parsed
