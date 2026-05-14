"""Document / submission lifecycle statuses and reviewer decision actions."""

from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    """Canonical lifecycle state for a submission or document.

    Stored verbatim in the ``status`` column on ``Submission`` and ``Document``.
    The same set of codes drives:
        - the ``DOCUMENT_STATUSES`` catalog returned to the frontend
        - reviewer queue filters
        - portal correction-flow gating
    """

    PENDIENTE = "pendiente"
    RECIBIDO = "recibido"
    PENDIENTE_REVISION = "pendiente_revision"
    PREVALIDADO = "prevalidado"
    POSIBLE_MISMATCH = "posible_mismatch"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    VENCIDO = "vencido"
    NO_APLICA = "no_aplica"
    REQUIERE_ACLARACION = "requiere_aclaracion"
    EXCEPCION_LEGAL = "excepcion_legal"


class ReviewerAction(StrEnum):
    """Decision a reviewer can apply to a submission awaiting review."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CLARIFICATION = "request_clarification"
    MARK_EXCEPTION = "mark_exception"


REVIEWER_DECISION_STATUS: dict[ReviewerAction, DocumentStatus] = {
    ReviewerAction.APPROVE: DocumentStatus.APROBADO,
    ReviewerAction.REJECT: DocumentStatus.RECHAZADO,
    ReviewerAction.REQUEST_CLARIFICATION: DocumentStatus.REQUIERE_ACLARACION,
    ReviewerAction.MARK_EXCEPTION: DocumentStatus.EXCEPCION_LEGAL,
}


REVIEW_PENDING_STATUSES: tuple[DocumentStatus, ...] = (
    DocumentStatus.PENDIENTE_REVISION,
    DocumentStatus.POSIBLE_MISMATCH,
)

RESOLVED_STATUSES: tuple[DocumentStatus, ...] = (
    DocumentStatus.APROBADO,
    DocumentStatus.RECHAZADO,
    DocumentStatus.EXCEPCION_LEGAL,
)


STATUS_LABELS_ES: dict[DocumentStatus, str] = {
    DocumentStatus.PENDIENTE: "Pendiente",
    DocumentStatus.RECIBIDO: "Recibido",
    DocumentStatus.PENDIENTE_REVISION: "Pendiente de revisión",
    DocumentStatus.PREVALIDADO: "Prevalidado",
    DocumentStatus.POSIBLE_MISMATCH: "Posible mismatch",
    DocumentStatus.APROBADO: "Aprobado",
    DocumentStatus.RECHAZADO: "Rechazado",
    DocumentStatus.VENCIDO: "Vencido",
    DocumentStatus.NO_APLICA: "No aplica",
    DocumentStatus.REQUIERE_ACLARACION: "Requiere aclaración",
    DocumentStatus.EXCEPCION_LEGAL: "Excepción legal",
}
