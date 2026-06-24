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
* ``LiveSATCFDIClient`` is a documented SKELETON. Wiring the real SOAP/REST call
  to ``https://consultaqr.facturaelectronica.sat.gob.mx/ConsultaCFDIService.svc``
  (and accepting SAT's ToS, handling its rate limits / availability, and the
  legal review that implies) is the remaining operator step. Until implemented
  it raises ``NotImplementedError`` so selecting ``live`` mode fails loudly
  rather than silently behaving like the stub.

``build_sat_cfdi_client`` returns the stub unless an operator explicitly sets
``SAT_CFDI_CLIENT_MODE=live``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

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


class LiveSATCFDIClient:
    """SKELETON for the real SAT consulta — OPERATOR/LEGAL step, not wired.

    Implementation sketch for whoever wires it (kept here so the contract is
    unambiguous): POST a SOAP envelope to the ConsultaCFDIService ``Consulta``
    operation with the ``expresion`` string
    ``?re=<emisor>&rr=<receptor>&tt=<total>&id=<uuid>``; parse ``CodigoEstatus``
    (``S - Comprobante obtenido satisfactoriamente`` vs not found) and ``Estado``
    (``Vigente`` / ``Cancelado``) into one of the four statuses; map any
    transport/availability error to ``not_verifiable`` (fail-open). Accepting
    SAT's terms of service, its rate limits, and the legal review of automated
    queries is the gating decision this skeleton intentionally does not make.
    """

    source = "sat_cfdi_live"

    def consultar(
        self,
        *,
        cfdi_uuid: str,
        emisor_rfc: str,
        receptor_rfc: str,
        total: str | None = None,
    ) -> SATConsultaResult:
        raise NotImplementedError(
            "LiveSATCFDIClient is a skeleton — wiring the real SAT consulta call "
            "and accepting SAT's terms of service is an operator/legal decision. "
            "Implement consultar() (see the class docstring) before setting "
            "SAT_CFDI_CLIENT_MODE=live."
        )


def build_sat_cfdi_client() -> SATCFDIClient:
    """Return the configured client. ``stub`` (default) unless an operator
    explicitly opts into ``live`` (which currently raises until implemented)."""
    mode = (settings.SAT_CFDI_CLIENT_MODE or "stub").strip().lower()
    if mode == "live":
        return LiveSATCFDIClient()
    return StubSATCFDIClient()
