"""SAT CFDI ``consulta`` client (B1 scaffolding).

The SAT exposes a public "Consulta de Comprobantes" service that, given a CFDI
fiscal UUID plus the emisor RFC, receptor RFC and (for full validation) the
total, returns whether the comprobante is ``Vigente`` or ``Cancelado`` and
whether it exists at all. Asking SAT directly is the moat: a stolen-real or
fabricated CFDI that passes the local QR/forensics checks still fails here.

This module is deliberately split so the LIVE network call is an explicit,
isolated OPERATOR/LEGAL decision:

* ``StubSATCFDIClient`` (default) makes ZERO network calls. It returns a canned
  status (``settings.SAT_CFDI_STUB_STATUS``) so the whole table + worker +
  verdict-plumbing path can be exercised end-to-end — in tests and in a dry-run
  on prod — without ever contacting SAT or accepting SAT's terms of service.
* ``LiveSATCFDIClient`` makes the real call: a hand-rolled SOAP ``Consulta`` to
  ``https://consultaqr.facturaelectronica.sat.gob.mx/ConsultaCFDIService.svc``
  over ``httpx`` + stdlib XML (no zeep/lxml dependency). It FAILS OPEN — any
  transport/HTTP/parse error or SOAP fault yields ``not_verifiable``, and only a
  *definitive* SAT answer ever produces ``vigente`` / ``cancelado`` / ``no_existe``.
  Selecting ``live`` is still an explicit OPERATOR/LEGAL decision (SAT ToS, rate
  limits) — it is just no longer blocked by missing code.

``build_sat_cfdi_client`` returns the stub unless an operator explicitly sets
``SAT_CFDI_CLIENT_MODE=live``.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# The four verdicts the worker + verdict plumbing understand. ``not_verifiable``
# is the fail-open verdict: stub mode, a transport error, or missing inputs.
STATUS_VIGENTE = "vigente"
STATUS_CANCELADO = "cancelado"
STATUS_NO_EXISTE = "no_existe"
STATUS_NOT_VERIFIABLE = "not_verifiable"

VALID_STATUSES = frozenset(
    {STATUS_VIGENTE, STATUS_CANCELADO, STATUS_NO_EXISTE, STATUS_NOT_VERIFIABLE}
)

# Statuses that INVALIDATE a document (drive the HIGH authenticity reason). A
# cancelled or non-existent CFDI is not a valid live invoice.
INVALIDATING_STATUSES = frozenset({STATUS_CANCELADO, STATUS_NO_EXISTE})


@dataclass(frozen=True)
class SATConsultaResult:
    """One SAT consulta outcome. ``raw`` keeps the provider response for audit."""

    status: str
    source: str
    raw: dict | None = None


class SATCFDIClient(Protocol):
    def consultar(
        self,
        *,
        cfdi_uuid: str,
        emisor_rfc: str,
        receptor_rfc: str,
        total: str | None = None,
    ) -> SATConsultaResult: ...


class StubSATCFDIClient:
    """No-network stub. Returns ``settings.SAT_CFDI_STUB_STATUS`` (default
    ``not_verifiable``) so the verdict plumbing is exercised without SAT."""

    source = "stub"

    def consultar(
        self,
        *,
        cfdi_uuid: str,
        emisor_rfc: str,
        receptor_rfc: str,
        total: str | None = None,
    ) -> SATConsultaResult:
        status = (settings.SAT_CFDI_STUB_STATUS or STATUS_NOT_VERIFIABLE).strip().lower()
        if status not in VALID_STATUSES:
            logger.warning(
                "SAT_CFDI_STUB_STATUS=%r is not a known status; using not_verifiable.",
                status,
            )
            status = STATUS_NOT_VERIFIABLE
        return SATConsultaResult(
            status=status,
            source=self.source,
            raw={"stub": True, "requested_status": status, "cfdi_uuid": cfdi_uuid},
        )


# ---- Live SAT consulta wiring -------------------------------------------------

_SAT_ENDPOINT = "https://consultaqr.facturaelectronica.sat.gob.mx/ConsultaCFDIService.svc"
_SAT_SOAP_ACTION = "http://tempuri.org/IConsultaCFDIService/Consulta"

_SOAP_TEMPLATE = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:tem="http://tempuri.org/">'
    "<soapenv:Body><tem:Consulta>"
    "<tem:expresionImpresa><![CDATA[{expresion}]]></tem:expresionImpresa>"
    "</tem:Consulta></soapenv:Body></soapenv:Envelope>"
)

# Fields we lift out of the ConsultaResult (kept in ``raw`` for audit).
_CONSULTA_FIELDS = frozenset(
    {"CodigoEstatus", "EsCancelable", "Estado", "EstatusCancelacion", "ValidacionEFOS"}
)


def _fmt_total(total: str | None) -> str:
    """Normalize the CFDI total for the ``tt`` field.

    SAT matches this value exactly against the comprobante; the precise decimal
    layout must be confirmed empirically against a known CFDI before live use
    (see the LiveSATCFDIClient implementation spec, Q1). Here we strip
    whitespace and thousands separators and pass the plain decimal through.
    """
    if total is None:
        return ""
    return str(total).strip().replace(",", "")


def _build_expresion(
    *, cfdi_uuid: str, emisor_rfc: str, receptor_rfc: str, total: str | None
) -> str:
    """Build the ``expresionImpresa`` query string. ``tt`` is omitted when no
    total is supplied (the caller may not have it yet — see spec §6)."""
    parts = [f"re={emisor_rfc}", f"rr={receptor_rfc}"]
    tt = _fmt_total(total)
    if tt:
        parts.append(f"tt={tt}")
    parts.append(f"id={cfdi_uuid}")
    return "?" + "&".join(parts)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_consulta(xml_text: str) -> dict:
    """Pull the ConsultaResult fields out of the SOAP response by localname
    (namespace-prefix agnostic). Raises on a SOAP Fault so the caller fails
    open to not_verifiable."""
    root = ET.fromstring(xml_text)
    fields: dict[str, str] = {}
    fault = False
    for el in root.iter():
        name = _localname(el.tag)
        if name == "Fault":
            fault = True
        elif name in _CONSULTA_FIELDS:
            fields[name] = (el.text or "").strip()
    if fault and not fields:
        raise ValueError("SAT returned a SOAP Fault")
    return fields


def _map_status(fields: dict) -> str:
    """Map a parsed ConsultaResult to one of our four statuses.

    Conservative on purpose: only a *definitive* SAT answer invalidates a
    document. ``CodigoEstatus 602`` ("Comprobante no encontrado") and an
    ``Estado`` of "No Encontrado" are genuine not-found verdicts; ``601``
    ("expresión impresa no es válida") usually means OUR query was malformed
    (e.g. a wrong/absent total) — that must NOT flag a real document, so it
    falls open to not_verifiable.
    """
    estado = (fields.get("Estado") or "").strip().lower()
    codigo = (fields.get("CodigoEstatus") or "").strip().lower()
    if estado == "vigente":
        return STATUS_VIGENTE
    if estado == "cancelado":
        return STATUS_CANCELADO
    if "no encontrad" in estado or "602" in codigo:
        return STATUS_NO_EXISTE
    return STATUS_NOT_VERIFIABLE


class LiveSATCFDIClient:
    """Live SAT ``Consulta`` client — hand-rolled SOAP over httpx + stdlib XML.

    FAIL-OPEN: any transport/HTTP error, SOAP fault, or unparseable response
    returns ``not_verifiable``; only a definitive SAT answer yields
    ``vigente`` / ``cancelado`` / ``no_existe``. ``transport`` is an injection
    seam for tests (pass an ``httpx.MockTransport``); production uses the default.

    Selecting this client (``SAT_CFDI_CLIENT_MODE=live``) remains an explicit
    operator/legal decision (SAT terms of service + rate limits).
    """

    source = "sat_cfdi_live"

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def consultar(
        self,
        *,
        cfdi_uuid: str,
        emisor_rfc: str,
        receptor_rfc: str,
        total: str | None = None,
    ) -> SATConsultaResult:
        expresion = _build_expresion(
            cfdi_uuid=cfdi_uuid,
            emisor_rfc=emisor_rfc,
            receptor_rfc=receptor_rfc,
            total=total,
        )
        envelope = _SOAP_TEMPLATE.format(expresion=expresion)
        timeout = float(settings.SAT_CFDI_TIMEOUT_SECONDS or 15)

        try:
            with httpx.Client(transport=self._transport, timeout=timeout) as client:
                resp = client.post(
                    _SAT_ENDPOINT,
                    content=envelope.encode("utf-8"),
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": _SAT_SOAP_ACTION,
                    },
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:  # timeout / conn / 5xx / etc.
            logger.warning(
                "SAT consulta transport error (%s); not_verifiable.",
                type(exc).__name__,
            )
            return SATConsultaResult(
                status=STATUS_NOT_VERIFIABLE,
                source=self.source,
                raw={"error": type(exc).__name__, "cfdi_uuid": cfdi_uuid},
            )

        try:
            fields = _parse_consulta(resp.text)
        except Exception as exc:  # noqa: BLE001 — malformed XML / fault → fail open
            logger.warning("SAT consulta parse error (%s); not_verifiable.", type(exc).__name__)
            return SATConsultaResult(
                status=STATUS_NOT_VERIFIABLE,
                source=self.source,
                raw={"parse_error": type(exc).__name__, "cfdi_uuid": cfdi_uuid},
            )

        return SATConsultaResult(status=_map_status(fields), source=self.source, raw=fields)


def build_sat_cfdi_client() -> SATCFDIClient:
    """Return the configured client. ``stub`` (default) unless an operator
    explicitly opts into ``live`` (which performs the real SAT consulta)."""
    mode = (settings.SAT_CFDI_CLIENT_MODE or "stub").strip().lower()
    if mode == "live":
        return LiveSATCFDIClient()
    return StubSATCFDIClient()
