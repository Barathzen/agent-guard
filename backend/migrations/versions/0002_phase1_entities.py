"""phase 1 entities

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Teams table
    op.create_table(
        'teams',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Agents table
    op.create_table(
        'agents',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('team_id', sa.String(length=64), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'PAUSED', 'ARCHIVED', name='agentstatus'), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('agent_id', sa.String(length=64), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'EXHAUSTED', 'CLOSED', name='sessionstatus'), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Budget policies table
    op.create_table(
        'budget_policies',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('scope', sa.Enum('TEAM', 'AGENT', 'SESSION', name='policyscope'), nullable=False),
        sa.Column('period', sa.Enum('MONTHLY', 'ROLLING_30_DAYS', 'SESSION_LIFETIME', name='budgetperiod'), nullable=False),
        sa.Column('limit_amount', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('warning_threshold_pct', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('team_id', sa.String(length=64), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=True),
        sa.Column('agent_id', sa.String(length=64), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=True),
        sa.Column('session_id', sa.String(length=64), sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('limit_amount >= 0', name='check_positive_limit'),
        sa.CheckConstraint('warning_threshold_pct > 0 AND warning_threshold_pct <= 100', name='check_valid_threshold')
    )

    # Connect budget_accounts to policies
    op.add_column('budget_accounts', sa.Column('policy_id', sa.String(length=64), sa.ForeignKey('budget_policies.id'), nullable=True))
    op.drop_column('budget_accounts', 'account_type')

def downgrade() -> None:
    op.add_column('budget_accounts', sa.Column('account_type', sa.VARCHAR(length=10), nullable=True))
    op.drop_column('budget_accounts', 'policy_id')
    op.drop_table('budget_policies')
    op.drop_table('sessions')
    op.drop_table('agents')
    op.drop_table('teams')