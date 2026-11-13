"""phase 7 model allocations

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_allocations",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("allocation_limit", sa.Numeric(14, 6), nullable=False),
        sa.Column("settled_spend", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("reserved_amount", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.CheckConstraint("allocation_limit >= 0", name="check_model_allocation_limit"),
        sa.UniqueConstraint("agent_id", "model_name", name="uq_model_allocation_agent_model"),
    )
    op.add_column(
        "reservations",
        sa.Column(
            "model_allocation_id",
            sa.String(96),
            sa.ForeignKey("model_allocations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("reservations", "model_allocation_id")
    op.drop_table("model_allocations")
