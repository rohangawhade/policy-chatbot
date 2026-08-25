"""add message policy_type, document last_queried_at, flagged_response ESCALATED status

Revision ID: d7ad8824e70e
Revises: 482316749c74
Create Date: 2026-08-25 16:53:41.028111

Three additive, Step 9.6-driven changes:
- `messages.policy_type` — reuses the existing `policy_type` Postgres enum
  (Step 1.3's ENUM lifecycle pattern: defined once at module level with
  `create_type=False` since the type already exists, never created/dropped
  here).
- `documents.last_queried_at` — plain nullable timestamp, no enum involved.
- `flagged_response_status` gains an `ESCALATED` value (files/plan.md's
  Step 9.6 `PATCH /api/admin/flagged-responses/{id}` — "mark as reviewed /
  dismiss / escalate" needs a third non-pending status). Postgres supports
  `ALTER TYPE ... ADD VALUE` directly; it has no `DROP VALUE` equivalent,
  so `downgrade()` rebuilds the type without it instead (same rename ->
  recreate -> cast -> drop-old technique used to shrink any enum).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d7ad8824e70e"
down_revision: str | None = "482316749c74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

policy_type_enum = postgresql.ENUM(
    "HEALTH", "DENTAL", "VISION", "LIFE", "DISABILITY", name="policy_type", create_type=False
)


def upgrade() -> None:
    op.execute("ALTER TYPE flagged_response_status ADD VALUE IF NOT EXISTS 'ESCALATED'")
    op.add_column(
        "documents", sa.Column("last_queried_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("messages", sa.Column("policy_type", policy_type_enum, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "policy_type")
    op.drop_column("documents", "last_queried_at")

    # No ALTER TYPE ... DROP VALUE in Postgres — rebuild the type without
    # ESCALATED. Fails if any row still has status='ESCALATED', which is
    # correct: a downgrade that would silently destroy that data shouldn't
    # succeed quietly.
    op.execute("ALTER TYPE flagged_response_status RENAME TO flagged_response_status_old")
    op.execute(
        "CREATE TYPE flagged_response_status AS ENUM " "('PENDING_REVIEW', 'REVIEWED', 'DISMISSED')"
    )
    op.execute(
        "ALTER TABLE flagged_responses ALTER COLUMN status TYPE flagged_response_status "
        "USING status::text::flagged_response_status"
    )
    op.execute("DROP TYPE flagged_response_status_old")
