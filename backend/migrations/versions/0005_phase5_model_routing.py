"""phase 5 model routing

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_capabilities",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_context_tokens", sa.Integer(), nullable=False, server_default="128000"),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("provider", "model_name", name="uq_model_capability_provider_name"),
    )
    op.create_table(
        "model_route_policies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "agent_id", sa.String(64), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("preferred_model", sa.String(64), nullable=False),
        sa.Column("allowed_models", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("fallback_models", sa.JSON(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("agent_id", name="uq_model_route_policy_agent"),
    )


def downgrade() -> None:
    op.drop_table("model_route_policies")
    op.drop_table("model_capabilities")
