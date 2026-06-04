"""Document **issuing source** for a requirement or submission.

Despite the name, an ``Institution`` is not always a government body — the
field answers "where does this document originate / who is its issuing
authority?", and one of the answers is "no government authority".

  * ``STPS_REPSE``, ``SAT``, ``IMSS``, ``INFONAVIT`` are real Mexican
    government authorities. Documents under these codes are downloaded from
    (or regulated by) that authority's portal and carry a regulatory period.

  * ``INTERNO_CLIENTE`` ("Interno / Cliente") is the **non-government** bucket:
    documents whose issuing source is the contractual relationship itself —
    the signed service contract, the acta constitutiva and its reformas,
    órdenes de servicio, official ID, and other Expediente Corporativo docs.
    The provider uploads these from their own legal archive or requests them
    from the client's legal area; they have no regulatory period (audit
    packages file them under ``sin-periodo``) and are always ordered last.

This is the single canonical definition; UI labels, audit folders, report
groupings, and metadata rules all defer to it. Per-role meaning:

  * Provider  — "comes from my own files / the client", not a gov portal.
  * Client    — documents the client itself requires (contract, corporate).
  * Reviewer  — a grouping key for reports, audit folders, metadata rules.

Note: the contract subset (``ONB-CONT-*``) is lifted into its own synthetic
``contrato`` group at audit-package time so it surfaces as a first-class
folder rather than being buried inside this bucket — see ``audit_package``.

Do not confuse this with ``MembershipRole.INTERNAL_ADMIN`` in ``roles.py``,
which is an unrelated *user role* (the Legal Shelf / CheckWise operator).
"""

from __future__ import annotations

from enum import StrEnum


class Institution(StrEnum):
    STPS_REPSE = "stps_repse"
    SAT = "sat"
    IMSS = "imss"
    INFONAVIT = "infonavit"
    INTERNO_CLIENTE = "interno_cliente"


INSTITUTION_LABELS: dict[Institution, str] = {
    Institution.STPS_REPSE: "STPS / REPSE",
    Institution.SAT: "SAT",
    Institution.IMSS: "IMSS",
    Institution.INFONAVIT: "INFONAVIT",
    Institution.INTERNO_CLIENTE: "Interno / Cliente",
}
