"""phase 4 atomic enforcement

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_warning_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("budget_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("threshold_pct", sa.Integer(), nullable=False),
        sa.Column("utilization_pct", sa.Numeric(7, 2), nullable=False),
        sa.Column("window_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "window_key", name="uq_budget_warning_account_window"),
    )


def downgrade() -> None:
    op.drop_table("budget_warning_events")
