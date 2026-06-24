"""Shared security gates for legacy / operator endpoints.

These dependencies exist so trust-boundary decisions are spelled out at
the route once and not scattered through individual handlers.

``require_local_or_internal_admin`` is the policy for endpoints that:
  * are needed locally without authentication (importer + dev workflows,
    integration tests, n8n prototyping), AND
  * must NOT be anonymously reachable in any non-local environment.

In ``CHECKWISE_ENV=local`` the dependency is a no-op. In every other
environment the request must carry a valid bearer JWT for a user that
holds the ``internal_admin`` role; otherwise the request is rejected
with 401 / 403 before any handler body runs.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, get_current_user
from app.constants.roles import STAFF_ROLES
from app.core.config import settings
from app.db.session import get_db


def require_local_or_internal_admin(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser | None:
    """No-op in local-anonymous calls. Outside local, demand internal_admin.

    Returns the resolved ``CurrentUser`` when an authenticated caller
    is present (so handlers can attribute actions to a user), or
    ``None`` in local-anonymous mode.
    """
    if settings.is_local_env and authorization is None:
        return None
    # Delegating to get_current_user keeps the JWT decode + active-user
    # check + must_change_password gate in one place. It raises 401 on
    # a bad/missing token even in local when one was attempted, and 403
    # when the caller is on the password-reset gate, which is the right
    # behavior.
    current = get_current_user(request, db, authorization=authorization)
    if not (STAFF_ROLES & set(current.roles)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="CheckWise staff role required",
        )
    return current
