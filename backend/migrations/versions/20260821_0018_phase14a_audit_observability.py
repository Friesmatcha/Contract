"""Add Phase 14A audit query index."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260821_0018"
down_revision: str | None = "20260821_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_logs_created_at_id",
        "audit_logs",
        ["created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at_id", table_name="audit_logs")
