"""Add a short-lived previous CSRF hash for concurrent session reads.

Revision ID: 20260818_0003
Revises: 20260817_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0003"
down_revision: str | None = "20260817_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("csrf_previous_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "auth_sessions",
        sa.Column("csrf_previous_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "csrf_previous_hash_valid",
        "auth_sessions",
        "csrf_previous_hash IS NULL OR char_length(csrf_previous_hash) = 64",
    )


def downgrade() -> None:
    op.drop_constraint("csrf_previous_hash_valid", "auth_sessions", type_="check")
    op.drop_column("auth_sessions", "csrf_previous_expires_at")
    op.drop_column("auth_sessions", "csrf_previous_hash")
