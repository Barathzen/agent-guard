"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'budget_accounts',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('account_type', sa.Enum('TEAM', 'AGENT', 'SESSION', name='accounttype'), nullable=False),
        sa.Column('budget_limit', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('settled_spend', sa.Numeric(precision=14, scale=6), nullable=False, server_default='0.000000'),
        sa.Column('reserved_amount', sa.Numeric(precision=14, scale=6), nullable=False, server_default='0.000000'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        'reservations',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('agent_id', sa.String(length=64), nullable=False),
        sa.Column('team_id', sa.String(length=64), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('estimated_cost', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('actual_cost', sa.Numeric(precision=14, scale=6), nullable=False, server_default='0.000000'),
        sa.Column('state', sa.Enum('RESERVED', 'SETTLED', 'RELEASED', 'UNKNOWN', name='reservationstate'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        'model_pricings',
        sa.Column('model_name', sa.String(length=64), primary_key=True),
        sa.Column('input_price_per_m', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('output_price_per_m', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('pricing_version', sa.String(length=32), nullable=False, server_default='v1')
    )

def downgrade() -> None:
    op.drop_table('model_pricings')
    op.drop_table('reservations')
    op.drop_table('budget_accounts')