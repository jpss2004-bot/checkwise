"""Document-revalidation Phase B — QR/folio extraction service.

Covers ``app.services.document_verification.extract_verification``:
QR decoding from PDF-embedded images (built in-test with Pillow pages
plus a zxing-cpp-rendered QR), the official-domain allowlist with
dot-boundary suffix matching, the two named risk reasons
(``qr_non_official_domain`` medium, ``missing_expected_qr`` info-only
this phase), folio regex extraction (CFDI UUID, opinion folios,
dedupe + cap), and the swallow-everything contract (garbage bytes
never raise — an extraction failure must NEVER block an upload).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image

from app.services.document_forensics import SEVERITY_INFO, SEVERITY_MEDIUM
from app.services.document_verification import (
    MAX_FOLIOS,
    OFFICIAL_VERIFICATION_DOMAINS,
    VerificationResult,
    extract_folios,
    extract_verification,
    is_official_host,
)

# ---------------------------------------------------------------------------
# PDF builders
# ---------------------------------------------------------------------------


def _qr_image(content: str) -> Image.Image:
    """Render a QR as a PIL image, preferring the non-deprecated API."""
    if hasattr(zxingcpp, "create_barcode") and hasattr(
        zxingcpp, "write_barcode_to_image"
    ):
        barcode = zxingcpp.create_barcode(content, zxingcpp.BarcodeFormat.QRCode)
        return Image.fromarray(zxingcpp.write_barcode_to_image(barcode))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return Image.fromarray(
            zxingcpp.write_barcode(content, zxingcpp.BarcodeFormat.QRCode)
        )


def _pdf_with_qr(tmp_path: Path, name: str, content: str) -> Path:
    """One-page PDF (Pillow page with a pasted QR image XObject)."""
    page = Image.new("RGB", (612, 792), "white")
    qr = _qr_image(content).convert("RGB").resize((220, 220), Image.NEAREST)
    page.paste(qr, (60, 60))
    path = tmp_path / name
    page.save(path, format="PDF")
    return path


def _pdf_without_qr(tmp_path: Path, name: str) -> Path:
    page = Image.new("RGB", (612, 792), "white")
    path = tmp_path / name
    page.save(path, format="PDF")
    return path


def _codes(result: VerificationResult) -> set[str]:
    return {reason.code for reason in result.reasons}


# ---------------------------------------------------------------------------
# QR extraction + official-domain classification
# ---------------------------------------------------------------------------


def test_official_sat_qr_decodes_clean(tmp_path: Path) -> None:
    url = "https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id=ABC-123"
    path = _pdf_with_qr(tmp_path, "sat.pdf", url)
    result = extract_verification(
        path, detected_institution="sat", extracted_text=None
    )

    assert result.analyzed is True
    assert len(result.qr_codes) == 1
    qr = result.qr_codes[0]
    assert qr["page"] == 1
    assert qr["content"] == url
    assert qr["is_url"] is True
    assert qr["host"] == "verificacfdi.facturaelectronica.sat.gob.mx"
    assert qr["official"] is True
    assert qr["institution_guess"] == "sat"
    # Official QR on a SAT doc: nothing to flag.
    assert result.reasons == []
    assert result.payload["error"] is None
    assert result.payload["qr_codes"] == result.qr_codes
    assert result.payload["pages_scanned"] == 1
    assert result.payload["images_scanned"] >= 1


def test_non_official_qr_on_sat_doc_is_medium(tmp_path: Path) -> None:
    path = _pdf_with_qr(
        tmp_path, "fake.pdf", "https://verificaciones-sat.com.mx/doc/999"
    )
    result = extract_verification(
        path, detected_institution="sat", extracted_text=None
    )

    assert result.qr_codes[0]["official"] is False
    assert _codes(result) == {"qr_non_official_domain"}
    reason = result.reasons[0]
    assert reason.severity == SEVERITY_MEDIUM
    assert "verificaciones-sat.com.mx" in reason.detail_es


def test_non_official_qr_without_institution_is_not_flagged(tmp_path: Path) -> None:
    path = _pdf_with_qr(tmp_path, "anon.pdf", "https://example.com/x")
    result = extract_verification(
        path, detected_institution=None, extracted_text=None
    )
    assert result.qr_codes[0]["official"] is False
    assert result.reasons == []


def test_official_suffix_must_be_dot_anchored(tmp_path: Path) -> None:
    """``sat.gob.mx.evil.com`` must NOT pass the allowlist."""
    path = _pdf_with_qr(tmp_path, "evil.pdf", "https://sat.gob.mx.evil.com/verifica")
    result = extract_verification(
        path, detected_institution=None, extracted_text=None
    )
    qr = result.qr_codes[0]
    assert qr["host"] == "sat.gob.mx.evil.com"
    assert qr["official"] is False
    assert qr["institution_guess"] is None


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("sat.gob.mx", True),
        ("verificacfdi.facturaelectronica.sat.gob.mx", True),
        ("serviciosdigitales.imss.gob.mx", True),
        ("portalmx.infonavit.org.mx", True),
        ("repse.stps.gob.mx", True),
        ("www.gob.mx", True),
        ("sat.gob.mx.evil.com", False),
        ("notsat.gob.mx.co", False),
        ("imss.gob.mx.phish.net", False),
        ("", False),
        (None, False),
    ],
)
def test_is_official_host_dot_boundaries(host: str | None, expected: bool) -> None:
    assert is_official_host(host) is expected


def test_allowlist_is_exported() -> None:
    assert "sat.gob.mx" in OFFICIAL_VERIFICATION_DOMAINS
    assert "infonavit.org.mx" in OFFICIAL_VERIFICATION_DOMAINS


def test_non_url_qr_content_is_stored_without_reasons(tmp_path: Path) -> None:
    payload = "REPSE|123456|ACME SERVICIOS SA DE CV"
    path = _pdf_with_qr(tmp_path, "plain.pdf", payload)
    result = extract_verification(
        path, detected_institution="sat", extracted_text=None
    )
    qr = result.qr_codes[0]
    assert qr["content"] == payload
    assert qr["is_url"] is False
    assert qr["host"] is None
    assert qr["official"] is False
    assert qr["institution_guess"] is None
    # A QR was decoded, so missing_expected_qr does not fire; non-URL
    # content never trips the domain check.
    assert result.reasons == []


# ---------------------------------------------------------------------------
# missing_expected_qr — info ONLY this phase
# ---------------------------------------------------------------------------


def test_missing_qr_on_institutional_doc_is_info_only(tmp_path: Path) -> None:
    path = _pdf_without_qr(tmp_path, "noqr.pdf")
    result = extract_verification(
        path, detected_institution="sat", extracted_text=None
    )
    assert result.qr_codes == []
    assert _codes(result) == {"missing_expected_qr"}
    reason = result.reasons[0]
    assert reason.severity == SEVERITY_INFO  # soft signal until harness data
    assert reason.detail_es == (
        "No se encontró un código QR de verificación; los documentos "
        "oficiales suelen incluirlo. (El documento puede usar un QR "
        "vectorial que el análisis no rasteriza.)"
    )


def test_missing_qr_without_institution_is_silent(tmp_path: Path) -> None:
    path = _pdf_without_qr(tmp_path, "noqr2.pdf")
    result = extract_verification(
        path, detected_institution=None, extracted_text=None
    )
    assert result.reasons == []


@pytest.mark.parametrize("institution", ["sat", "imss", "infonavit", "stps_repse"])
def test_missing_qr_fires_for_every_official_institution(
    tmp_path: Path, institution: str
) -> None:
    path = _pdf_without_qr(tmp_path, f"noqr-{institution}.pdf")
    result = extract_verification(
        path, detected_institution=institution, extracted_text=None
    )
    assert _codes(result) == {"missing_expected_qr"}


# ---------------------------------------------------------------------------
# Folio extraction
# ---------------------------------------------------------------------------


def test_cfdi_uuid_extracted_and_deduped() -> None:
    uuid = "ad662d33-6934-459c-a128-bdf0393e0f44"
    text = f"Folio fiscal: {uuid}\n...\nFolio fiscal (repetido): {uuid.upper()}"
    folios = extract_folios(text)
    assert folios == [{"kind": "cfdi_uuid", "value": uuid.upper()}]


def test_sat_and_imss_opinion_folios_extracted() -> None:
    text = (
        "SERVICIO DE ADMINISTRACION TRIBUTARIA (SAT)\n"
        "Opinión del cumplimiento de obligaciones fiscales\n"
        "Folio: 24NA1234567890\n"
        "----\n"
        "IMSS — Opinión de cumplimiento\n"
        "Folio de verificación: IMSS-2026-00077123\n"
    )
    folios = extract_folios(text)
    kinds = {f["kind"]: f["value"] for f in folios}
    assert kinds["sat_opinion_folio"] == "24NA1234567890"
    assert kinds["imss_opinion_folio"] == "IMSS-2026-00077123"


def test_folio_requires_digits_to_skip_all_caps_words() -> None:
    text = "SAT folio CONSTANCIA-DE-REGISTRO pendiente"
    assert extract_folios(text) == []


def test_folios_capped_at_ten() -> None:
    uuids = [f"ad662d33-6934-459c-a128-bdf0393e0f{n:02d}" for n in range(15)]
    text = "\n".join(f"Folio fiscal: {u}" for u in uuids)
    folios = extract_folios(text)
    assert len(folios) == MAX_FOLIOS == 10


def test_folio_extraction_tolerates_none() -> None:
    assert extract_folios(None) == []
    assert extract_folios("") == []


def test_extracted_text_param_feeds_folios(tmp_path: Path) -> None:
    """When the caller retained text, the service must not re-read it."""
    path = _pdf_without_qr(tmp_path, "folio.pdf")
    uuid = "AD662D33-6934-459C-A128-BDF0393E0F44"
    result = extract_verification(
        path,
        detected_institution=None,
        extracted_text=f"Comprobante CFDI folio fiscal {uuid}",
    )
    assert result.folios == [{"kind": "cfdi_uuid", "value": uuid}]
    assert result.payload["folios"] == result.folios


# ---------------------------------------------------------------------------
# Fail-open contract + payload shape
# ---------------------------------------------------------------------------


def test_garbage_file_fails_open_with_error(tmp_path: Path) -> None:
    path = tmp_path / "garbage.pdf"
    path.write_bytes(b"%PDF-1.7 totalmente roto \x00\x01\x02 sin xref")
    result = extract_verification(
        path, detected_institution="sat", extracted_text=None
    )
    assert result.analyzed is False
    assert result.qr_codes == []
    assert result.folios == []
    assert result.reasons == []
    assert result.payload["error"]


def test_missing_file_never_raises(tmp_path: Path) -> None:
    result = extract_verification(
        tmp_path / "no-existe.pdf", detected_institution="sat", extracted_text=None
    )
    assert result.analyzed is False
    assert result.payload["error"]


def test_payload_shape_is_stable(tmp_path: Path) -> None:
    path = _pdf_without_qr(tmp_path, "shape.pdf")
    result = extract_verification(
        path, detected_institution=None, extracted_text=None
    )
    assert set(result.payload) == {
        "qr_codes",
        "folios",
        "pages_scanned",
        "images_scanned",
        "error",
    }
    assert set(result.qr_codes[0]) if result.qr_codes else True


def test_qr_entry_shape(tmp_path: Path) -> None:
    path = _pdf_with_qr(tmp_path, "shape-qr.pdf", "https://www.gob.mx/imss/verifica")
    result = extract_verification(
        path, detected_institution=None, extracted_text=None
    )
    assert set(result.qr_codes[0]) == {
        "page",
        "content",
        "is_url",
        "host",
        "official",
        "institution_guess",
    }
    # gob.mx federal portal is official, but the bare domain names no
    # specific institution.
    assert result.qr_codes[0]["official"] is True
    assert result.qr_codes[0]["institution_guess"] is None
