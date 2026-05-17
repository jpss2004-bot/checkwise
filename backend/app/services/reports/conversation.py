"""Conversation service for the embedded report copilot.

Operates against the ``report_conversations`` table created in 3.1.
The schema is open — `content_json` is a typed-dict-shaped JSON
blob — so this service is responsible for owning the turn-content
contract.

Turn-content shapes (matches the architecture spec §10):

  text turn       { "kind": "text", "markdown": "..." }
  plan_card turn  { "kind": "plan_card", "plan": {...}, "status": "..." }
  patch_card turn { "kind": "patch_card", "patches": [...], "status": "..." }
  tool_call turn  { "kind": "tool_call", "tool": "...", "args": {...} }
  tool_result     { "kind": "tool_result", "tool_call_id": "...", "result": ... }
  error turn      { "kind": "error", "code": "...", "message": "..." }

Phase 3.3c ships text turns only. The plan_card / patch_card flow is
specced in architecture but deliberately deferred to a 2.2 polish
phase — for v1 the copilot returns text + lets the user pick a block
type from the existing palette.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.reports import ConversationRole
from app.models.entities import ReportConversation, new_id, utc_now
from app.services.report_service import ReportActor


def list_conversation(
    db: Session, *, report_id: str, limit: int = 200
) -> list[ReportConversation]:
    """Return the full conversation in ascending turn order.

    The copilot in 3.3c sees the last 12 turns in its LLM prompt
    (the recency window); the UI shows all of them for context.
    """
    stmt = (
        select(ReportConversation)
        .where(ReportConversation.report_id == report_id)
        .order_by(ReportConversation.turn_number.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def append_turn(
    db: Session,
    *,
    report_id: str,
    role: ConversationRole,
    content: dict,
    attached_version_id: str | None = None,
    actor: ReportActor | None = None,
) -> ReportConversation:
    """Append one turn atomically. turn_number is auto-incremented."""
    next_n = (
        db.scalar(
            select(func.max(ReportConversation.turn_number)).where(
                ReportConversation.report_id == report_id
            )
        )
        or 0
    ) + 1
    turn = ReportConversation(
        id=new_id(),
        report_id=report_id,
        turn_number=next_n,
        role=role.value,
        content_json=content,
        attached_version_id=attached_version_id,
        created_by_user_id=actor.user_id if actor else None,
        created_at=utc_now(),
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return turn


def recent_messages_for_llm(
    db: Session, *, report_id: str, window: int = 12
) -> Iterable[dict]:
    """Render the last ``window`` turns as Anthropic-compatible
    `{role, content}` dicts.

    Only text-shaped turns are emitted. plan_card / patch_card turns
    are skipped (the proposed-changes UI doesn't need to be re-fed
    to the model). System turns become assistant-context preludes.
    """
    stmt = (
        select(ReportConversation)
        .where(ReportConversation.report_id == report_id)
        .order_by(ReportConversation.turn_number.desc())
        .limit(window)
    )
    raw = list(db.scalars(stmt))
    raw.reverse()  # back to ascending order for the LLM
    out: list[dict] = []
    for t in raw:
        content = t.content_json or {}
        kind = content.get("kind")
        text = content.get("markdown") if kind == "text" else None
        if not text:
            continue
        # Anthropic expects 'user'|'assistant'. Map system/tool turns
        # to 'assistant' for context; they won't be re-emitted.
        role = "user" if t.role == ConversationRole.USER.value else "assistant"
        out.append({"role": role, "content": text})
    return out


def text_turn(markdown: str) -> dict:
    """Builder helper for the text-turn shape."""
    return {"kind": "text", "markdown": markdown}


def error_turn(code: str, message: str) -> dict:
    return {"kind": "error", "code": code, "message": message}
