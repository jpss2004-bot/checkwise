"""Submission + Document workflow state machine.

Single owner of all reviewer- and legal-driven status transitions on
``Submission`` (and the primary ``Document``). Before Phase 2, the
reviewer endpoint mutated ``Submission.status`` and built history /
event rows by hand; it did not touch ``Document.status`` or emit an
``audit_log`` entry. Those gaps are closed here.

Scope:

* In scope — reviewer decisions (approve / reject / request_clarification /
  mark_exception) and any future legal/admin state moves on a submission
  that is already in the system.
* Out of scope (for now) — the *initial* status set at intake. That is
  written by :func:`app.services.submission_service.finalize_intake_submission`
  along with the rest of the intake pipeline. Moving initial intake into
  this workflow service is a future cleanup but would only restate what
  intake already does atomically — see ``docs/WORKFLOW_STATE_MACHINE.md``.

Design choices:

* Allowed *source* statuses are the same queue statuses the reviewer
  surface lists (``recibido``, ``pendiente_revision``, ``prevalidado``,
  ``posible_mismatch``) plus ``requiere_aclaracion`` — the latter means
  the ball is back in the provider's court but a reviewer can still
  re-decide if a clarification arrived out-of-band. ``RESOLVED_STATUSES``
  (``aprobado`` / ``rechazado`` / ``excepcion_legal``) are terminal: a
  new attempt is required to move forward. This matches existing
  reviewer-endpoint behavior 1:1 so no test regresses.
* The service raises ``HTTPException`` directly, matching the pattern
  used by :mod:`app.services.requirement_service`. The router stays a
  thin shell.
* The service commits internally. Same pattern as
  :func:`finalize_intake_submission`. Reviewer decisions are atomic —
  status mutation, history row, validation event, and audit log all
  succeed or all roll back as a unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import (
    RESOLVED_STATUSES,
    REVIEWER_DECISION_STATUS,
    DocumentStatus,
    ReviewerAction,
)
from app.models import Document, DocumentStatusHistory, Submission
from app.models.entities import utc_now
from app.services.audit_log import add_audit_event
from app.services.client_notifications import notify_reviewer_decision
from app.services.provider_notifications import (
    notify_provider_of_reviewer_decision,
)
from app.services.transactional_email import (
    email_provider_of_reviewer_decision,
)
from app.services.validation_events import add_validation_event

# Reviewer actions that demand a free-text reason from the user. Approve
# is the only action that does not — approval is the positive signal and
# the reason is implicit ("the document is correct").
_ACTIONS_REQUIRING_REASON: frozenset[ReviewerAction] = frozenset(
    {
        ReviewerAction.REJECT,
        ReviewerAction.REQUEST_CLARIFICATION,
        ReviewerAction.MARK_EXCEPTION,
    }
)


# Statuses from which a reviewer decision is allowed. Anything in
# ``RESOLVED_STATUSES`` is terminal and produces a 409 from
# :func:`apply_reviewer_decision`. ``no_aplica`` is intentionally NOT
# treated as a queue source today — there is no UX path that puts a
# submission in ``no_aplica`` then asks a reviewer to act on it. If
# that changes, add it here explicitly so the rule stays auditable.
_DECISION_SOURCE_STATUSES: frozenset[DocumentStatus] = frozenset(
    {
        DocumentStatus.RECIBIDO,
        DocumentStatus.PENDIENTE_REVISION,
        DocumentStatus.PREVALIDADO,
        DocumentStatus.POSIBLE_MISMATCH,
        DocumentStatus.REQUIERE_ACLARACION,
    }
)


@dataclass(frozen=True)
class TransitionResult:
    """The outcome of a successful reviewer decision.

    Returned to the router so it can shape the API response without
    re-loading the submission. ``previous_status`` and ``new_status``
    are the canonical string codes (matching the existing
    ``DecisionResponse`` schema). ``decided_at`` is the timestamp the
    workflow service applied to ``Submission.updated_at`` — the router
    surfaces it as the decision time.
    """

    submission_id: str
    document_id: str | None
    previous_status: str
    new_status: str
    action: str
    reason: str | None
    # Phase 9 / Slice 9A — optional reviewer observation rendered
    # alongside (but distinct from) the formal reason. Mirrors the
    # API contract on ``DecisionResponse``.
    observations: str | None
    reviewer_user_id: str
    decided_at: datetime


def is_terminal_status(value: str | DocumentStatus) -> bool:
    """Return True iff ``value`` is a resolved/terminal submission status.

    Wraps :data:`RESOLVED_STATUSES` so callers don't have to compare
    against a tuple of enum members. Accepts either a raw string (the
    DB-stored form) or a :class:`DocumentStatus` member.
    """
    try:
        status_enum = DocumentStatus(value) if not isinstance(value, DocumentStatus) else value
    except ValueError:
        return False
    return status_enum in RESOLVED_STATUSES


def _resolve_action(action: str | ReviewerAction) -> ReviewerAction:
    if isinstance(action, ReviewerAction):
        return action
    try:
        return ReviewerAction(action)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Acción de revisor desconocida: {action!r}.",
        ) from exc


def _validate_transition(submission: Submission, target: ReviewerAction) -> None:
    """Reject terminal sources and unsupported transitions."""
    try:
        current = DocumentStatus(submission.status)
    except ValueError as exc:
        # Unknown status in the DB shouldn't happen, but if it does we
        # surface it loudly rather than silently overwriting it.
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                f"Submission tiene un estado no reconocido ({submission.status!r}); "
                "no se puede aplicar una decisión hasta corregir el dato."
            ),
        ) from exc

    if current in RESOLVED_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Submission already resolved as '{current.value}'.",
        )

    if current not in _DECISION_SOURCE_STATUSES:
        # Statuses like ``pendiente``, ``vencido``, ``no_aplica`` shouldn't
        # be transitioned via a reviewer decision. Surface a 409 so the
        # caller can react instead of silently overwriting.
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                f"No se permite una decisión de revisor desde el estado "
                f"'{current.value}'."
            ),
        )
    # ``target`` is currently never invalid because every ReviewerAction
    # maps to a supported target status in REVIEWER_DECISION_STATUS, but
    # we leave the hook here so future actions (e.g. ``reopen``) can be
    # gated per-source-status without restructuring the service.
    _ = target


# Phase E — canonical Spanish reason stamped on every automatic
# approval. Flows verbatim into ``DocumentStatusHistory.reason``,
# ``ValidationEvent.message`` and both notification bodies so the
# client/provider-facing timeline reads distinctly from a human
# reviewer's approval.
AUTO_APPROVAL_REASON_ES = (
    "Aprobado automáticamente por el sistema de validación documental."
)


def apply_reviewer_decision(
    db: Session,
    *,
    submission: Submission,
    action: str | ReviewerAction,
    reason: str | None,
    reviewer_user_id: str,
    observations: str | None = None,
    accepted_suggestion: bool | None = None,
) -> TransitionResult:
    """Apply a reviewer decision to a submission as an atomic transition.

    Validates the action and the current submission status, then mutates
    ``Submission.status`` and ``Document.status`` (for the primary
    document, if one exists), writes a ``DocumentStatusHistory`` row,
    a ``ValidationEvent`` with ``event_type='reviewer_decision'``, and
    an ``AuditLog`` entry. The whole batch is committed in one
    transaction — partial writes cannot escape.

    Raises:
        HTTPException(409): submission is already in a terminal status,
            or the action is not allowed from the current status.
        HTTPException(422): action is unknown, or the action requires a
            reason and ``reason`` is empty / whitespace-only.

    Audit trail:
        * ``DocumentStatusHistory(actor='reviewer:<user_id>')``
        * ``ValidationEvent(actor_type='reviewer', result=<action>)``
        * ``AuditLog(action='submission.reviewer_decision',
          actor_type='reviewer', actor_id=<user_id>,
          before={'status': previous}, after={'status': new},
          metadata={'reviewer_action', 'reason', 'document_id'})``

    The audit trail is intentionally redundant: status history is the
    timeline shown to the provider, validation events feed the
    reviewer-facing event log, and the audit log is the cross-entity
    compliance record. Each one answers a different question.
    """
    action_enum = _resolve_action(action)

    cleaned_reason = (reason or "").strip() or None
    if action_enum in _ACTIONS_REQUIRING_REASON and not cleaned_reason:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"'{action_enum.value}' requires a 'reason'.",
        )
    # Slice 9A — observations are always optional. Whitespace-only
    # input collapses to None so the notification body doesn't render
    # a stray "Observación: " heading with empty content.
    cleaned_observations = (observations or "").strip() or None

    _validate_transition(submission, action_enum)

    audit_metadata: dict = {
        "reviewer_action": action_enum.value,
        "reason": cleaned_reason,
        # Slice 9A — observations are stored only on the audit
        # log + the notification bodies; intentionally NOT on
        # DocumentStatusHistory.reason / ValidationEvent.message
        # so the provider-facing timeline keeps reading as one
        # clean reason per row.
        "observations": cleaned_observations,
    }
    # Phase E — suggestion-acceptance telemetry. Only present when the
    # client explicitly reported whether the reviewer followed the
    # approval suggestion; absence of the key means "no suggestion
    # interaction was reported", which is the pre-Phase-E behavior.
    if accepted_suggestion is not None:
        audit_metadata["suggestion"] = {
            "shown": True,
            "accepted": bool(accepted_suggestion),
        }

    return _apply_decision_transition(
        db,
        submission=submission,
        action_enum=action_enum,
        reason=cleaned_reason,
        observations=cleaned_observations,
        history_actor=f"reviewer:{reviewer_user_id}",
        event_actor_type="reviewer",
        event_payload_extra={"reviewer_user_id": reviewer_user_id},
        audit_action="submission.reviewer_decision",
        audit_actor_type="reviewer",
        audit_actor_id=reviewer_user_id,
        audit_metadata_extra=audit_metadata,
        result_reviewer_user_id=reviewer_user_id,
        notification_reviewer_user_id=reviewer_user_id,
    )


def apply_system_auto_approval(
    db: Session,
    *,
    submission: Submission,
    evidence: dict,
) -> TransitionResult:
    """Apply an automatic approval with system actor semantics (Phase E).

    Same atomic transition + side effects as a reviewer's approve
    (``Submission.status`` / ``Document.status`` → ``aprobado``,
    ``DocumentStatusHistory``, ``ValidationEvent``, ``AuditLog``,
    client + provider notifications, email/WhatsApp best-effort), but:

    * History/event actor is ``"system"`` (no ``reviewer:<id>``).
    * The audit action is ``system.auto_approved`` and its metadata
      carries the FULL eligibility evidence snapshot assembled by
      :func:`app.services.auto_approval.maybe_auto_approve`.
    * The reason is :data:`AUTO_APPROVAL_REASON_ES`, so every
      downstream timeline reads distinctly from a human approval.

    Raises the same 409s as a reviewer decision when the submission is
    terminal or in a non-decidable status — callers (the auto-approval
    engine) pre-validate eligibility and treat any raise as a no-op.
    """
    _validate_transition(submission, ReviewerAction.APPROVE)
    return _apply_decision_transition(
        db,
        submission=submission,
        action_enum=ReviewerAction.APPROVE,
        reason=AUTO_APPROVAL_REASON_ES,
        observations=None,
        history_actor="system",
        event_actor_type="system",
        event_payload_extra={"source": "auto_approval"},
        audit_action="system.auto_approved",
        audit_actor_type="system",
        audit_actor_id=None,
        audit_metadata_extra=dict(evidence),
        result_reviewer_user_id="system",
        notification_reviewer_user_id=None,
    )


def _apply_decision_transition(
    db: Session,
    *,
    submission: Submission,
    action_enum: ReviewerAction,
    reason: str | None,
    observations: str | None,
    history_actor: str,
    event_actor_type: str,
    event_payload_extra: dict,
    audit_action: str,
    audit_actor_type: str,
    audit_actor_id: str | None,
    audit_metadata_extra: dict,
    result_reviewer_user_id: str,
    notification_reviewer_user_id: str | None,
) -> TransitionResult:
    """Shared decision-application core (reviewer + system callers).

    Owns the status mutation and EVERY downstream side effect so the
    Phase-E auto-approve engine cannot drift from the human path:
    history, validation event, audit log, client/provider
    notifications, transactional email and WhatsApp all live here
    exactly once. Callers differ only in actor semantics (who decided)
    and audit framing (action + metadata). Commits internally; the
    whole batch succeeds or rolls back as a unit.
    """
    # TOCTOU guard (audit 2026-06-21, Batch 6): the caller validated
    # ``submission.status`` against the terminal/source guard, then we
    # mutate and commit — a check-then-act with no row lock. A human
    # ``apply_reviewer_decision`` can run concurrently with the
    # background shadow runner's ``apply_system_auto_approval`` on the
    # SAME submission: both read a non-terminal status, both pass the
    # guard, and the second commit overwrites the first's terminal
    # status, leaving two terminal transitions for one row.
    #
    # Re-load the row ``with_for_update()`` and re-run the terminal/
    # source guard INSIDE the lock. The second concurrent writer blocks
    # on the row lock, then re-reads the now-terminal status and bails
    # with the existing 409 — which the auto-approval engine already
    # treats as a no-op ("transition_failed"). On SQLite ``with_for_update``
    # is silently ignored (tests unaffected); the re-select + re-check is
    # a harmless no-op there. Single-threaded behavior is unchanged.
    locked = db.scalar(
        select(Submission).where(Submission.id == submission.id).with_for_update()
    )
    if locked is None:
        # The submission vanished between the caller's load and here
        # (extremely unlikely). Treat it like a lost race rather than a
        # 500 on a stale ORM object.
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="La submission ya no existe; no se puede aplicar la decisión.",
        )
    # Re-bind to the locked row so the mutation below writes the row we
    # hold the lock on (it is the same identity-mapped object in
    # practice, but be explicit) and re-validate under the lock.
    submission = locked
    _validate_transition(submission, action_enum)

    cleaned_reason = reason
    cleaned_observations = observations

    previous_status = submission.status
    target_status = REVIEWER_DECISION_STATUS[action_enum]
    new_status_value = target_status.value
    transition_at = utc_now()

    submission.status = new_status_value
    submission.updated_at = transition_at

    # Phase 2 — fix the gap: keep ``Document.status`` in sync with the
    # submission's status for the primary document. Pre-Phase-2 the
    # reviewer endpoint only updated ``Submission.status`` and left the
    # document row drifting on its intake-time value.
    document = db.scalar(
        select(Document).where(Document.submission_id == submission.id).limit(1)
    )
    document_id = document.id if document is not None else None
    if document is not None:
        document.status = new_status_value
        document.updated_at = transition_at

    db.add(
        DocumentStatusHistory(
            submission_id=submission.id,
            document_id=document_id,
            from_status=previous_status,
            to_status=new_status_value,
            reason=cleaned_reason,
            actor=history_actor,
        )
    )

    add_validation_event(
        db,
        submission_id=submission.id,
        document_id=document_id,
        event_type="reviewer_decision",
        rule_code="reviewer_decision",
        result=action_enum.value,
        severity="info" if action_enum == ReviewerAction.APPROVE else "warning",
        message=cleaned_reason,
        actor_type=event_actor_type,
        payload={
            **event_payload_extra,
            "from_status": previous_status,
            "to_status": new_status_value,
        },
    )

    add_audit_event(
        db,
        action=audit_action,
        entity_type="submission",
        entity_id=submission.id,
        actor_type=audit_actor_type,
        actor_id=audit_actor_id,
        before={"status": previous_status},
        after={"status": new_status_value},
        metadata={
            **audit_metadata_extra,
            "document_id": document_id,
        },
    )

    notify_reviewer_decision(
        db,
        submission=submission,
        action=action_enum,
        reason=cleaned_reason,
        observations=cleaned_observations,
    )
    # Phase 4 / Slice 4B — also fire a provider-side notification so
    # the inbox at /portal/notifications surfaces the decision next
    # to the existing /client/notifications row. Returns None and
    # short-circuits silently when no workspace matches the
    # (client_id, vendor_id) — protects the reviewer flow against
    # legacy or partial-seed submissions.
    notify_provider_of_reviewer_decision(
        db,
        submission=submission,
        action=action_enum,
        reason=cleaned_reason,
        observations=cleaned_observations,
    )
    # Junta 2026-05-25 — transactional email outbound. Best-effort: a
    # SMTP failure or a user with ``contact_preference="whatsapp"``
    # returns a "skipped"/"failed" result without raising, so the
    # reviewer's decision still commits cleanly. The in-app
    # ProviderNotification above is the canonical delivery.
    from app.core.config import settings as _settings

    try:
        email_provider_of_reviewer_decision(
            db,
            submission=submission,
            action=action_enum.value,
            reason=cleaned_reason,
            observations=cleaned_observations,
            portal_base_url=_settings.FRONTEND_BASE_URL,
        )
    except Exception:  # pragma: no cover — defensive
        import logging as _logging

        _logging.getLogger("checkwise.submission_workflow").exception(
            "[submission_workflow] outbound email crashed; decision still committed"
        )

    # M-WA (2026-05-25) — WhatsApp delivery for users on
    # contact_preference={"whatsapp","both"}. Independent of email
    # above: failure on one channel never blocks the other or the
    # underlying decision. The reviewer's display name (if found via
    # the reviewer_user_id) becomes the "by {{4}}" slot in the
    # template — defaults to "Legal Shelf" when absent.
    try:
        from app.models import User as _User
        from app.services.transactional_whatsapp import (
            whatsapp_provider_of_reviewer_decision,
        )

        reviewer_name: str | None = None
        if notification_reviewer_user_id:
            reviewer_user = db.get(_User, notification_reviewer_user_id)
            if reviewer_user is not None:
                reviewer_name = reviewer_user.full_name or reviewer_user.email

        whatsapp_provider_of_reviewer_decision(
            db,
            submission=submission,
            action=action_enum.value,
            reviewer_name=reviewer_name,
        )
    except Exception:  # pragma: no cover — defensive
        import logging as _logging

        _logging.getLogger("checkwise.submission_workflow").exception(
            "[submission_workflow] outbound whatsapp crashed; decision still committed"
        )

    db.commit()
    db.refresh(submission)

    return TransitionResult(
        submission_id=submission.id,
        document_id=document_id,
        previous_status=previous_status,
        new_status=new_status_value,
        action=action_enum.value,
        reason=cleaned_reason,
        observations=cleaned_observations,
        reviewer_user_id=result_reviewer_user_id,
        decided_at=submission.updated_at,
    )
