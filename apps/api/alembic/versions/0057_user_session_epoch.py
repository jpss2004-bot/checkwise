"""User session epoch (JWT revocation stamp).

Revision ID: 0057_user_session_epoch
Revises: 0063_intake_queue
Create Date: 2026-06-24

Rechained onto main's head ``0063_intake_queue`` during the
F6/codex → main integration (2026-06-25). It was authored against the
codex branch's ``0056_rename_rbac_roles``, which main renumbered to
``0060_rename_rbac_roles`` — so the original down_revision dangled and
broke ``alembic upgrade head``. The migration itself is purely additive
(one column), so applying it last is order-independent and safe.

Adds ``users.session_epoch`` so the API can revoke outstanding access
tokens without waiting for their natural 24h expiry (CW-AUTHZ-001 /
CW-AUTH-001 / CW-AUTH-002). The epoch is minted into every JWT at login
and compared against this column in ``get_current_user``; it is bumped on

- password reset / set-password (terminate all sessions on recovery),
- staff role revocation (a revoked role takes effect immediately), and
- client seat demotion (an Approver → Viewer change drops write access).

Column (additive):
- ``users.session_epoch`` — INT NOT NULL default 0.

``server_default='0'`` stamps every existing row to 0, which matches the
``se`` default for pre-migration tokens (decoded as 0), so the deploy does
NOT mass-log-out live sessions.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0057_user_session_epoch"
down_revision = "0063_intake_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "session_epoch",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "session_epoch")
