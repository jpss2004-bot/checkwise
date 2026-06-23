"""Client-side user management — the 3-seat model.

Multi-user step 2 (2026-06-10, after migration 0037; seat tiers 2026-06).
A client organization holds up to ``seat_limit`` user accounts (3 by
default, the Primary Account Owner included). Each seat carries one of
two tiers — ``client_admin`` (Approver: full write, manages the team and
the portfolio) or ``client_viewer`` (read + export only). *Managing* the
seats (create, disable, remove, reset, change tier) is open to any
Approver of the org and to CheckWise support staff; Viewers are
read-only. The cap counts every active seat regardless of tier.

Semantics:

* **Create** — mirrors the admin provisioning flow: temp password,
  ``must_change_password=True``, branded welcome email. No invite
  tokens in v1. If the email belongs to a user previously *removed*
  from this same org (and inert everywhere else), the seat is
  reinstated with fresh credentials instead of 409ing — otherwise
  a removed employee's email would be permanently burned.
* **Disable** (reversible) — flips ``User.status``. The auth
  dependency re-reads the row per request, so lockout is immediate;
  the seat stays occupied until the user is removed.
* **Remove** (frees the seat) — membership → ``removed`` and the
  User row is disabled when no other active membership exists. The
  row is never deleted: every historical ``actor_id`` must keep
  resolving for the REPSE audit trail. "Reassign a slot" = remove,
  then create the replacement.
* **Reset password** — owner-issued temp credentials for a secondary
  who is locked out. The primary resets their own via the standard
  ``/forgot-password`` flow.

Seat-cap discipline: the organization row is locked (``SELECT …
FOR UPDATE``) before counting active memberships, so two concurrent
creates cannot both land in the last seat. On SQLite (tests) the
lock is a no-op — the cap there is still enforced, just not under
true concurrency. ``seat_limit`` NULL on a client org falls back to
``DEFAULT_CLIENT_SEAT_LIMIT`` defensively (orgs created before the
service layer started stamping the column).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser
from app.api.v1.client import ClientUser, DbSession, _resolve_client_id
from app.constants.roles import STAFF_ROLES, MembershipRole
from app.core.config import settings
from app.core.rate_limit import client_ip_from_request
from app.models import Client, Membership, Organization, PasswordHistory, User
from app.services.audit_log import add_audit_event
from app.services.auth import generate_temp_password, hash_password
from app.services.email_delivery import (
    send_owner_reset_temp_password_email,
    send_welcome_with_temp_password_email,
)
from app.services.subscription import org_for_client

router = APIRouter(prefix="/client/users", tags=["client-users"])

# Fallback when ``organizations.seat_limit`` is NULL on a client org.
# Mirrors the migration-0037 backfill value.
DEFAULT_CLIENT_SEAT_LIMIT = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_ctx(request: Request) -> dict:
    """IP + user-agent for the audit row (platform rework Phase 6).
    ``user_agent`` is truncated to the AuditLog column width."""
    ua = request.headers.get("user-agent")
    return {
        "ip_address": client_ip_from_request(request),
        "user_agent": ua[:512] if ua else None,
    }


def _is_internal(current: CurrentUser) -> bool:
    """True for CheckWise staff (review team or superadmin) — they get
    cross-tenant support access to client seat management."""
    return bool(STAFF_ROLES & set(current.roles))


def _actor_type(current: CurrentUser) -> str:
    if MembershipRole.OPERATIONS_ADMIN.value in current.roles:
        return MembershipRole.OPERATIONS_ADMIN.value
    if MembershipRole.PLATFORM_ADMIN.value in current.roles:
        return MembershipRole.PLATFORM_ADMIN.value
    return MembershipRole.CLIENT_ADMIN.value


def _org_for_client(
    db: Session, client_id: str, *, for_update: bool = False
) -> Organization:
    """The ``kind='client'`` organization bridging to this Client row.

    Thin alias over the canonical resolver in the subscription service so
    the seats surface and the provider-limit surface share one
    implementation (404s when absent; provisioning creates exactly one).
    """
    return org_for_client(db, client_id, for_update=for_update)


def _holds_approver_seat(
    db: Session, current: CurrentUser, org: Organization
) -> bool:
    """True when the caller holds an active ``client_admin`` (Approver) seat
    in this org. Approvers manage their own team — create, disable, remove,
    reset and change the tier of other seats (the Primary Owner is always
    protected; see ``_reject_primary_target``)."""
    seat = db.scalar(
        select(Membership.id).where(
            Membership.organization_id == org.id,
            Membership.user_id == current.user.id,
            Membership.role == MembershipRole.CLIENT_ADMIN.value,
            Membership.status == "active",
        )
    )
    return seat is not None


def _can_manage(db: Session, current: CurrentUser, org: Organization) -> bool:
    """Seat management is open to any Approver of the org plus CheckWise
    support staff. Viewers are read-only."""
    return _is_internal(current) or _holds_approver_seat(db, current, org)


def _require_can_manage(
    db: Session, current: CurrentUser, org: Organization
) -> None:
    if not _can_manage(db, current, org):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=(
                "Solo un Aprobador puede administrar los usuarios de la "
                "organización."
            ),
        )


def _seat_limit(org: Organization) -> int:
    return org.seat_limit if org.seat_limit is not None else DEFAULT_CLIENT_SEAT_LIMIT


def _active_seats(db: Session, org_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
        )
        or 0
    )


def _active_membership_or_404(
    db: Session, org_id: str, user_id: str
) -> Membership:
    row = db.scalars(
        select(Membership).where(
            Membership.organization_id == org_id,
            Membership.user_id == user_id,
            Membership.status == "active",
        )
    ).first()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="El usuario no pertenece a esta organización.",
        )
    return row


def _reject_primary_target(membership: Membership) -> None:
    if membership.is_primary:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "El titular de la cuenta no puede modificarse desde "
                "esta pantalla."
            ),
        )


def _other_active_memberships(
    db: Session, user_id: str, exclude_org_id: str
) -> int:
    """Active memberships the target holds OUTSIDE this org.

    A secondary created by this flow belongs to exactly one org, but
    the schema allows more. Disabling ``User.status`` is global, so
    refusing to disable/remove a multi-org user from here prevents a
    client owner from locking that person out of an unrelated tenant.
    """
    return int(
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.user_id == user_id,
                Membership.organization_id != exclude_org_id,
                Membership.status == "active",
            )
        )
        or 0
    )


def _push_password_history(db: Session, user: User) -> None:
    """Record the hash being replaced (lazily, like
    ``auth._apply_password_change``). The next regular password
    change runs the depth trim; an untrimmed extra row only sits
    past the ``LIMIT`` of the reuse check."""
    if user.password_hash:
        db.add(
            PasswordHistory(user_id=user.id, password_hash=user.password_hash)
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ClientUserItem(BaseModel):
    user_id: str
    email: str
    full_name: str
    is_primary: bool
    role: str
    """``client_admin`` (Approver — full write) | ``client_viewer`` (read +
    export only). The Primary Owner is always a ``client_admin``."""
    status: str
    """``active`` | ``disabled`` — mirror of ``User.status``."""
    pending_first_login: bool
    """True while ``must_change_password`` is set (hasn't activated)."""
    last_login_at: str | None
    joined_at: str


class ClientUsersList(BaseModel):
    client_id: str
    organization_id: str
    seat_limit: int
    """Maximum number of seats (any tier), the Primary Owner included."""
    seats_used: int
    """Active seats of any tier (against ``seat_limit``)."""
    seats_available: int
    can_manage: bool
    """Whether the requesting user may manage seats — create, disable, reset,
    remove, change tier. True for any Approver of the org or CheckWise staff;
    False for read-only Viewers."""
    users: list[ClientUserItem]


class CreateClientUserPayload(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    # Seat tier. Defaults to the least-privilege Viewer; an Approver may
    # create another Approver by passing ``client_admin`` explicitly.
    role: Literal["client_admin", "client_viewer"] = "client_viewer"


class UpdateClientUserRolePayload(BaseModel):
    role: Literal["client_admin", "client_viewer"]


class ClientUserRoleResponse(BaseModel):
    user_id: str
    role: str


class CreateClientUserResponse(BaseModel):
    """``temp_password`` is plaintext, returned ONCE for the owner's
    confirmation screen — the User row only stores the bcrypt hash."""

    user_id: str
    email: str
    full_name: str
    temp_password: str
    login_url: str
    email_status: str
    email_error: str | None = None
    reinstated: bool = False
    seats_used: int
    seat_limit: int


class UpdateClientUserPayload(BaseModel):
    status: Literal["active", "disabled"]


class ClientUserActionResponse(BaseModel):
    user_id: str
    status: str
    seats_used: int
    seat_limit: int


class ResetClientUserPasswordResponse(BaseModel):
    user_id: str
    email: str
    temp_password: str
    email_status: str
    email_error: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ClientUsersList)
def list_client_users(
    db: DbSession,
    current: ClientUser,
    request: Request,
    client_id: str | None = Query(default=None),
) -> ClientUsersList:
    """Seated users of the organization (active memberships only).

    Read access for every member — secondaries can see who shares
    the account; only the owner sees mutation affordances
    (``can_manage``).
    """
    cid = _resolve_client_id(db, current, requested=client_id)
    org = _org_for_client(db, cid)

    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == org.id,
            Membership.status == "active",
        )
        .order_by(Membership.is_primary.desc(), Membership.created_at.asc())
    ).all()

    is_staff = _is_internal(current)
    holds_approver = any(
        m.user_id == current.user.id
        and m.role == MembershipRole.CLIENT_ADMIN.value
        for m, _ in rows
    )
    # Seat management (create / disable / reset / remove / change tier) is
    # open to any Approver of the org plus CheckWise support staff.
    can_manage = is_staff or holds_approver
    limit = _seat_limit(org)
    seats_used = len(rows)  # active memberships of any tier
    return ClientUsersList(
        client_id=cid,
        organization_id=org.id,
        seat_limit=limit,
        seats_used=seats_used,
        seats_available=max(0, limit - seats_used),
        can_manage=can_manage,
        users=[
            ClientUserItem(
                user_id=u.id,
                email=u.email,
                full_name=u.full_name,
                is_primary=m.is_primary,
                role=m.role,
                status=u.status,
                pending_first_login=u.must_change_password,
                last_login_at=(
                    u.last_login_at.isoformat() if u.last_login_at else None
                ),
                joined_at=m.created_at.isoformat(),
            )
            for m, u in rows
        ],
    )


@router.post(
    "",
    response_model=CreateClientUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a secondary user in the client organization",
)
def create_client_user(
    payload: CreateClientUserPayload,
    db: DbSession,
    current: ClientUser,
    request: Request,
    client_id: str | None = Query(default=None),
) -> CreateClientUserResponse:
    cid = _resolve_client_id(db, current, requested=client_id)
    # Lock the org row BEFORE counting seats so two concurrent creates
    # cannot both observe a free slot.
    org = _org_for_client(db, cid, for_update=True)

    # Seat management (creating either tier) is open to Approvers of the org
    # and to CheckWise staff. Viewers are read-only.
    _require_can_manage(db, current, org)

    full_name = payload.full_name.strip()
    email = payload.email.strip().lower()
    limit = _seat_limit(org)

    reinstate_user: User | None = None
    reinstate_membership: Membership | None = None
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        # Reinstate path: the email belongs to a user previously
        # removed from THIS org and inert everywhere else. Anything
        # else (active account, other tenant's user) is a 409.
        removed_here = db.scalars(
            select(Membership).where(
                Membership.organization_id == org.id,
                Membership.user_id == existing.id,
                Membership.status == "removed",
            )
        ).first()
        active_anywhere = int(
            db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.user_id == existing.id,
                    Membership.status == "active",
                )
            )
            or 0
        )
        if (
            existing.status != "active"
            and removed_here is not None
            and active_anywhere == 0
        ):
            reinstate_user = existing
            reinstate_membership = removed_here
        else:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Ya existe una cuenta con ese correo.",
            )

    # The cap counts every active seat regardless of tier. Both a brand-new
    # user and a reinstated (previously removed) one occupy a fresh slot.
    if _active_seats(db, org.id) >= limit:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Tu plan permite un máximo de {limit} usuarios. Elimina uno "
                "para liberar un lugar."
            ),
        )

    temp_password = generate_temp_password()
    if reinstate_user is not None and reinstate_membership is not None:
        user = reinstate_user
        _push_password_history(db, user)
        user.password_hash = hash_password(temp_password)
        user.full_name = full_name
        user.status = "active"
        user.must_change_password = True
        reinstate_membership.status = "active"
        reinstate_membership.is_primary = False
        reinstate_membership.role = payload.role
    else:
        user = User(
            email=email,
            password_hash=hash_password(temp_password),
            full_name=full_name,
            status="active",
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=payload.role,
                is_primary=False,
                status="active",
            )
        )
    db.flush()

    client_row = db.get(Client, cid)
    login_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/login"
    delivery = send_welcome_with_temp_password_email(
        to_email=email,
        full_name=full_name,
        login_url=login_url,
        temp_password=temp_password,
        role="client",
        organization_name=client_row.name if client_row else None,
    )

    # Total active seats AFTER this create.
    db.flush()
    seats_used = _active_seats(db, org.id)

    add_audit_event(
        db,
        action="client.user_created",
        entity_type="user",
        entity_id=user.id,
        actor_type=_actor_type(current),
        actor_id=current.user.id,
        **_request_ctx(request),
        after={
            "client_id": cid,
            "organization_id": org.id,
            "user_email": user.email,
            "reinstated": reinstate_user is not None,
            "role": payload.role,
            "seats_used": seats_used,
            "seat_limit": limit,
            "email_delivery_status": delivery.status,
        },
    )

    # Same companion emit as the admin provisioning flow (in-app bell
    # + SMS); never gates the response.
    try:
        import logging

        from app.services.notifications import emit_invitation_sent

        emit_invitation_sent(
            db,
            user=user,
            invitation_token_id=user.id,
            invitation_url=login_url,
            mode="active",
        )
        db.flush()
    except Exception:  # pragma: no cover — defensive
        logging.getLogger("checkwise.client_users").exception(
            "notif_emit_failed event=account.invitation_sent user=%s", user.id
        )

    db.commit()

    return CreateClientUserResponse(
        user_id=user.id,
        email=email,
        full_name=full_name,
        temp_password=temp_password,
        login_url=login_url,
        email_status=delivery.status,
        email_error=delivery.error,
        reinstated=reinstate_user is not None,
        seats_used=seats_used,
        seat_limit=limit,
    )


@router.patch(
    "/{user_id}",
    response_model=ClientUserActionResponse,
    summary="Disable or re-enable a secondary user",
)
def update_client_user(
    user_id: str,
    payload: UpdateClientUserPayload,
    db: DbSession,
    current: ClientUser,
    request: Request,
    client_id: str | None = Query(default=None),
) -> ClientUserActionResponse:
    cid = _resolve_client_id(db, current, requested=client_id)
    org = _org_for_client(db, cid)
    _require_can_manage(db, current, org)

    membership = _active_membership_or_404(db, org.id, user_id)
    _reject_primary_target(membership)

    if payload.status == "disabled" and _other_active_memberships(
        db, user_id, org.id
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "El usuario pertenece a otra organización; contacta a "
                "soporte para desactivarlo."
            ),
        )

    target = db.get(User, user_id)
    before_status = target.status
    target.status = payload.status

    add_audit_event(
        db,
        action=(
            "client.user_disabled"
            if payload.status == "disabled"
            else "client.user_reactivated"
        ),
        entity_type="user",
        entity_id=user_id,
        actor_type=_actor_type(current),
        actor_id=current.user.id,
        **_request_ctx(request),
        before={"status": before_status},
        after={
            "status": payload.status,
            "client_id": cid,
            "organization_id": org.id,
        },
    )
    db.commit()

    return ClientUserActionResponse(
        user_id=user_id,
        status=payload.status,
        seats_used=_active_seats(db, org.id),
        seat_limit=_seat_limit(org),
    )


@router.delete(
    "/{user_id}",
    response_model=ClientUserActionResponse,
    summary="Remove a secondary user and free their seat",
)
def remove_client_user(
    user_id: str,
    db: DbSession,
    current: ClientUser,
    request: Request,
    client_id: str | None = Query(default=None),
) -> ClientUserActionResponse:
    cid = _resolve_client_id(db, current, requested=client_id)
    org = _org_for_client(db, cid)
    _require_can_manage(db, current, org)

    membership = _active_membership_or_404(db, org.id, user_id)
    _reject_primary_target(membership)

    membership.status = "removed"
    target = db.get(User, user_id)
    # The User row stays (audit attribution must keep resolving);
    # disable it unless the person is active in another tenant.
    if not _other_active_memberships(db, user_id, org.id):
        target.status = "disabled"

    add_audit_event(
        db,
        action="client.user_removed",
        entity_type="user",
        entity_id=user_id,
        actor_type=_actor_type(current),
        actor_id=current.user.id,
        **_request_ctx(request),
        after={
            "client_id": cid,
            "organization_id": org.id,
            "user_email": target.email,
            "user_status": target.status,
        },
    )
    db.commit()

    return ClientUserActionResponse(
        user_id=user_id,
        status="removed",
        seats_used=_active_seats(db, org.id),
        seat_limit=_seat_limit(org),
    )


@router.post(
    "/{user_id}/reset-password",
    response_model=ResetClientUserPasswordResponse,
    summary="Issue fresh temp credentials to a secondary user",
)
def reset_client_user_password(
    user_id: str,
    db: DbSession,
    current: ClientUser,
    request: Request,
    client_id: str | None = Query(default=None),
) -> ResetClientUserPasswordResponse:
    cid = _resolve_client_id(db, current, requested=client_id)
    org = _org_for_client(db, cid)
    _require_can_manage(db, current, org)

    membership = _active_membership_or_404(db, org.id, user_id)
    _reject_primary_target(membership)

    target = db.get(User, user_id)
    if target.status != "active":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Reactiva al usuario antes de restablecer su contraseña.",
        )

    temp_password = generate_temp_password()
    _push_password_history(db, target)
    target.password_hash = hash_password(temp_password)
    target.must_change_password = True

    client_row = db.get(Client, cid)
    login_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/login"
    delivery = send_owner_reset_temp_password_email(
        to_email=target.email,
        full_name=target.full_name,
        login_url=login_url,
        temp_password=temp_password,
        organization_name=client_row.name if client_row else None,
    )

    add_audit_event(
        db,
        action="client.user_password_reset",
        entity_type="user",
        entity_id=user_id,
        actor_type=_actor_type(current),
        actor_id=current.user.id,
        **_request_ctx(request),
        after={
            "client_id": cid,
            "organization_id": org.id,
            "user_email": target.email,
            "email_delivery_status": delivery.status,
        },
    )
    db.commit()

    return ResetClientUserPasswordResponse(
        user_id=user_id,
        email=target.email,
        temp_password=temp_password,
        email_status=delivery.status,
        email_error=delivery.error,
    )


@router.patch(
    "/{user_id}/role",
    response_model=ClientUserRoleResponse,
    summary="Change a seat's access tier (Approver / Viewer)",
)
def update_client_user_role(
    user_id: str,
    payload: UpdateClientUserRolePayload,
    db: DbSession,
    current: ClientUser,
    request: Request,
    client_id: str | None = Query(default=None),
) -> ClientUserRoleResponse:
    """Promote a seat to ``client_admin`` (Approver) or demote it to
    ``client_viewer`` (read + export only).

    Both promotion and demotion are open to any Approver of the org (plus
    CheckWise staff) via ``_require_can_manage`` — a client manages its own
    team. The Primary Owner is always an Approver and cannot be demoted here.

    Role staleness, by case: a promoted/demoted user's JWT still carries the
    OLD role until they re-login (claims are minted at login). For a
    PROMOTION this is harmless (new Approver writes only work after the next
    sign-in). A DEMOTION is the security-relevant inverse: seat management is
    revoked immediately (that gate, ``_require_can_manage``, is DB-live), but
    the claims-based ``ClientApprover`` write gate (provider create/archive,
    profile edit) keeps honoring the stale token until it expires (≤24h).
    Closing that window — live role authorization on the client write gate —
    is tracked as follow-up work alongside client self-review.
    """
    cid = _resolve_client_id(db, current, requested=client_id)
    org = _org_for_client(db, cid)
    _require_can_manage(db, current, org)

    membership = _active_membership_or_404(db, org.id, user_id)
    _reject_primary_target(membership)

    before_role = membership.role
    if before_role != payload.role:
        membership.role = payload.role
        add_audit_event(
            db,
            action="client.user_role_changed",
            entity_type="user",
            entity_id=user_id,
            actor_type=_actor_type(current),
            actor_id=current.user.id,
            **_request_ctx(request),
            before={"role": before_role},
            after={
                "role": payload.role,
                "client_id": cid,
                "organization_id": org.id,
            },
        )
        db.commit()

    return ClientUserRoleResponse(user_id=user_id, role=payload.role)
