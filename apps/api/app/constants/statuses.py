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


# Canonical Spanish display labels. MUST stay word-for-word identical to
# the web app's glossary (apps/web/lib/constants/statuses.ts ::
# STATUS_LABELS_ES, vocabulary unification 2026-06-10) so a status reads
# the same in /catalogs responses, PDF exports and on-screen badges.
# Status CODES never change — only the display strings are unified:
#   - recibido / pendiente_revision / prevalidado collapse to
#     "En revisión" (a client can't act on the distinction),
#   - rechazado reads "Requiere corrección" (Audit P1-02 softening),
#   - excepcion_legal reads "Aprobado con nota legal" (it's a positive
#     outcome, not an alarm).
STATUS_LABELS_ES: dict[DocumentStatus, str] = {
    # Unified with the missing-slot label (2026-06-19): "no submission yet"
    # reads "Por entregar" everywhere, matching the frontend mirror.
    DocumentStatus.PENDIENTE: "Por entregar",
    DocumentStatus.RECIBIDO: "En revisión",
    DocumentStatus.PENDIENTE_REVISION: "En revisión",
    DocumentStatus.PREVALIDADO: "En revisión",
    DocumentStatus.POSIBLE_MISMATCH: "Posible inconsistencia",
    DocumentStatus.APROBADO: "Aprobado",
    DocumentStatus.RECHAZADO: "Requiere corrección",
    DocumentStatus.VENCIDO: "Vencido",
    DocumentStatus.NO_APLICA: "No aplica",
    DocumentStatus.REQUIERE_ACLARACION: "Necesita aclaración",
    DocumentStatus.EXCEPCION_LEGAL: "Aprobado con nota legal",
}
