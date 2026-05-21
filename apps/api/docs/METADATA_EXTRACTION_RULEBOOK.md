# CheckWise Metadata Extraction Rulebook

This backend catalog is the first safe implementation step toward AI-assisted document intelligence and an eventual n8n prototype.

## Scope

Created in this patch:

- `app/core/metadata_rules.py`
- `tests/test_metadata_rules.py`
- `docs/METADATA_EXTRACTION_RULEBOOK.md`

Not created in this patch:

- No database migration
- No OCR
- No AI/model call
- No Google Sheets connection
- No change to the upload/submission flow

## Purpose

The Legal Shelf PDF defines how CheckWise provider documents should be named and parameterized. This catalog converts that operational rulebook into typed, testable Python data so that future workflows can ask:

> For this document type, what fields are required and what must remain human-reviewed?

## n8n bridge

The future n8n workflow should not contain the legal/document logic directly. It should call or consume the CheckWise rulebook and then orchestrate file movement, extraction attempts, human review, and exports.

Recommended future order:

1. Metadata rulebook catalog and tests
2. Local JSON/template export
3. n8n workflow prototype using the JSON template
4. Local PDF parsing
5. OCR/AI only after the schema is stable
6. Google Sheets export only after review rules exist

## Verification

From the backend directory:

```bash
.venv/bin/ruff check app/core/metadata_rules.py tests/test_metadata_rules.py
.venv/bin/pytest tests/test_metadata_rules.py
```

The new tests are intentionally isolated from FastAPI, SQLAlchemy, the database, and the current upload flow.
