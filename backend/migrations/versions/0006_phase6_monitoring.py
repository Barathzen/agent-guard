"""phase 6 monitoring

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("team_id", sa.String(64), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_agent_id", "audit_events", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_agent_id", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
