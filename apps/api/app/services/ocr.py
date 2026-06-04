"""Google Document AI OCR client for scanned PDF uploads.

Phase 3 of the prevalidation hardening plan. Before Phase 3, scanned
PDFs (`inspect_pdf.is_probably_scanned=True`) landed in
``pendiente_revision`` with zero detector signals — the keyword bag
had no text to chew on. This service runs OCR synchronously during
intake when the upload is scanned, so the detector gets a fair shot.

Design choices:

* Synchronous, called from inside the intake transaction. Document AI
  usually returns in 2-6s; the timeout is capped by
  ``settings.OCR_TIMEOUT_SECONDS`` (default 30s).
* Triggered ONLY when ``is_probably_scanned=True`` — born-digital PDFs
  already have extractable text; OCR adds cost and latency without
  improving accuracy.
* Returns ``None`` on every failure path (no creds, missing config,
  API error, timeout). The caller treats ``None`` as "OCR unavailable,
  fall back to today's behavior" — intake never fails because of OCR.
* Lazy import of ``google.cloud.documentai`` so the backend boots in
  environments that don't have the GCP SDK installed (CI, dev).

See ``apps/api/docs/PHASE3_DOCUMENTAI_SETUP.md`` for the one-time GCP
provisioning checklist.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrResult:
    """Outcome of an OCR call.

    ``text`` is the extracted plain text on success, empty string on
    every failure. ``error`` carries a short human-readable label of
    why OCR didn't return text (for diagnostics / future metrics) —
    never surfaced to the provider.
    """

    text: str
    error: str | None = None
    page_count: int | None = None


class DocumentAiOcrClient:
    """Thin wrapper around the Google Document AI Document OCR processor.

    The client is constructed once at startup (or on first use) via
    ``build_ocr_client_from_settings``. ``extract_text`` is the only
    surface the rest of the codebase needs; it returns an ``OcrResult``
    that the caller folds into the existing ``PdfInspectionResult``.
    """

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        processor_id: str,
        credentials_path: str | None,
        timeout_seconds: float,
    ) -> None:
        # Lazy import — only required when OCR is actually enabled.
        from google.api_core.client_options import ClientOptions
        from google.cloud import documentai

        self._documentai = documentai
        self._timeout = timeout_seconds

        client_options = ClientOptions(
            api_endpoint=f"{location}-documentai.googleapis.com",
        )
        if credentials_path:
            self._client = documentai.DocumentProcessorServiceClient.from_service_account_json(
                credentials_path, client_options=client_options
            )
        else:
            # Fall back to standard ADC — the SDK reads
            # GOOGLE_APPLICATION_CREDENTIALS automatically.
            self._client = documentai.DocumentProcessorServiceClient(
                client_options=client_options
            )

        # processor_name format: projects/PROJECT/locations/LOCATION/processors/PROCESSOR_ID
        self._processor_name = self._client.processor_path(project_id, location, processor_id)

    @property
    def processor_name(self) -> str:
        """Fully-qualified Document AI processor path used for OCR calls.

        Surfaced so the intake layer can record which processor produced a
        scanned document's text in the ``ocr_performed`` audit event.
        """
        return self._processor_name

    def extract_text(self, pdf_path: Path) -> OcrResult:
        """Run Document AI OCR on a single PDF and return the plain text.

        Catches every exception path the underlying SDK can raise
        (network, auth, quota, invalid PDF, timeout) and returns an
        ``OcrResult`` with an empty string + a label. The intake flow
        is expected to treat this as "no OCR text available" and fall
        through to the pre-Phase-3 behavior.
        """
        try:
            pdf_bytes = pdf_path.read_bytes()
        except OSError as exc:
            logger.warning("ocr_read_failed path=%s error=%s", pdf_path, exc)
            return OcrResult(text="", error="read_failed")

        try:
            raw_document = self._documentai.RawDocument(
                content=pdf_bytes, mime_type="application/pdf"
            )
            request = self._documentai.ProcessRequest(
                name=self._processor_name, raw_document=raw_document
            )
            response = self._client.process_document(
                request=request, timeout=self._timeout
            )
        except Exception as exc:
            # Document AI surfaces a long list of failure modes
            # (PermissionDenied, NotFound, InvalidArgument,
            # DeadlineExceeded, ResourceExhausted, ...). Treat them
            # uniformly here — the caller cannot meaningfully recover
            # from any of them mid-intake, and we never want OCR
            # failures to abort an upload.
            logger.warning(
                "ocr_call_failed path=%s processor=%s error=%s",
                pdf_path,
                self._processor_name,
                exc,
            )
            return OcrResult(text="", error=type(exc).__name__)

        document = response.document
        text = getattr(document, "text", "") or ""
        pages = getattr(document, "pages", None)
        page_count = len(pages) if pages is not None else None
        return OcrResult(text=text, page_count=page_count)


def build_ocr_client_from_settings(
    config: Settings | None = None,
) -> DocumentAiOcrClient | None:
    """Return a configured client, or ``None`` if OCR is disabled / unconfigured.

    Returning ``None`` is the "OCR not available" signal the intake
    flow already handles. The pre-flight checks here protect against
    booting with half-configured env: if ``OCR_ENABLED=true`` but the
    processor ID is empty, we log a warning and return ``None`` rather
    than constructing a client that will 404 on every call.
    """
    config = config or settings
    if not config.OCR_ENABLED:
        return None

    missing = [
        name
        for name, value in (
            ("GOOGLE_DOC_AI_PROJECT_ID", config.GOOGLE_DOC_AI_PROJECT_ID),
            ("GOOGLE_DOC_AI_LOCATION", config.GOOGLE_DOC_AI_LOCATION),
            ("GOOGLE_DOC_AI_PROCESSOR_ID", config.GOOGLE_DOC_AI_PROCESSOR_ID),
        )
        if not (value or "").strip()
    ]
    if missing:
        logger.warning(
            "ocr_enabled_but_config_incomplete missing=%s", ",".join(missing)
        )
        return None

    credentials_path = _resolve_credentials_path(config)

    try:
        return DocumentAiOcrClient(
            project_id=config.GOOGLE_DOC_AI_PROJECT_ID,
            location=config.GOOGLE_DOC_AI_LOCATION,
            processor_id=config.GOOGLE_DOC_AI_PROCESSOR_ID,
            credentials_path=credentials_path,
            timeout_seconds=config.OCR_TIMEOUT_SECONDS,
        )
    except ImportError as exc:
        # ``google-cloud-documentai`` not installed. Should not happen
        # in production (pyproject pins it), but defensive: keep
        # intake working in dev environments that haven't installed
        # the optional GCP packages.
        logger.warning("ocr_sdk_unavailable error=%s", exc)
        return None
    except Exception as exc:
        # Bad credentials JSON, malformed location, etc. — any
        # construction failure means OCR is effectively unavailable.
        logger.warning("ocr_client_init_failed error=%s", exc)
        return None


def _resolve_credentials_path(config: Settings) -> str | None:
    """Return a service-account-JSON path the Google SDK can read.

    Two supported sources, in priority order:

    1. ``GOOGLE_APPLICATION_CREDENTIALS_JSON`` — inline JSON content.
       We write it to a per-process temp file so the SDK can read it
       like a normal key file. Render's env tab makes pasting JSON
       the easiest way to ship credentials.
    2. ``GOOGLE_APPLICATION_CREDENTIALS`` — the standard env var the
       SDK reads automatically. We return ``None`` here so the SDK's
       Application-Default-Credentials path runs unchanged.
    """
    inline = (config.GOOGLE_APPLICATION_CREDENTIALS_JSON or "").strip()
    if not inline:
        return None
    try:
        # Validate JSON before writing so we don't leave a junk file on
        # disk. We don't validate the keys — Google's SDK will reject
        # a malformed payload at first use.
        json.loads(inline)
    except json.JSONDecodeError as exc:
        logger.warning("ocr_credentials_json_invalid error=%s", exc)
        return None

    tmp = tempfile.NamedTemporaryFile(
        prefix="checkwise-gcp-sa-",
        suffix=".json",
        delete=False,
        mode="w",
        encoding="utf-8",
    )
    tmp.write(inline)
    tmp.flush()
    tmp.close()
    return tmp.name
