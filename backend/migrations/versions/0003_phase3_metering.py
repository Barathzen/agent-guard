"""phase 3 metering

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("model_pricings_pkey", "model_pricings", type_="primary")
    op.add_column("model_pricings", sa.Column("id", sa.String(96), nullable=True))
    op.add_column("model_pricings", sa.Column("provider", sa.String(64), nullable=True))
    op.add_column("model_pricings", sa.Column("currency", sa.String(3), nullable=True))
    op.add_column("model_pricings", sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("model_pricings", sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE model_pricings SET id = 'legacy-' || model_name, provider = 'mock', "
        "currency = 'USD', effective_from = '1970-01-01T00:00:00+00:00', pricing_version = COALESCE(pricing_version, 'v1')"
    )
    op.alter_column("model_pricings", "id", nullable=False)
    op.alter_column("model_pricings", "provider", nullable=False)
    op.alter_column("model_pricings", "currency", nullable=False)
    op.alter_column("model_pricings", "effective_from", nullable=False)
    op.create_primary_key("model_pricings_pkey", "model_pricings", ["id"])

    op.execute(
        sa.text(
            "INSERT INTO model_pricings "
            "(id, provider, model_name, input_price_per_m, output_price_per_m, currency, effective_from, pricing_version) "
            "VALUES ('mock-mock-gpt-4o-v1', 'mock', 'mock-gpt-4o', 1.000000, 2.000000, 'USD', CURRENT_TIMESTAMP, 'v1') "
            "ON CONFLICT (id) DO NOTHING"
        )
    )
    op.create_table(
        "usage_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("team_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("pricing_version", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_output_tokens", sa.Integer(), nullable=False),
        sa.Column("actual_input_tokens", sa.Integer(), nullable=False),
        sa.Column("actual_output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(14, 6), nullable=False),
        sa.Column("actual_cost", sa.Numeric(14, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_usage_records_request_id"),
    )


def downgrade() -> None:
    op.drop_table("usage_records")
    op.drop_constraint("model_pricings_pkey", "model_pricings", type_="primary")
    op.drop_column("model_pricings", "effective_to")
    op.drop_column("model_pricings", "effective_from")
    op.drop_column("model_pricings", "currency")
    op.drop_column("model_pricings", "provider")
    op.drop_column("model_pricings", "id")
    op.create_primary_key("model_pricings_pkey", "model_pricings", ["model_name"])
