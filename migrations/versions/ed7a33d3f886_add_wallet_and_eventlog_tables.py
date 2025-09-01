"""add wallet/event_log tables (idempotent)

Revision ID: ed7a33d3f886
Revises: ed7a33d3f885
Create Date: 2025-09-01 06:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ed7a33d3f886'
down_revision = 'ed7a33d3f885'
branch_labels = None
depends_on = None


def _table_exists(inspector, name: str) -> bool:
    try:
        return name in inspector.get_table_names()
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # creator_daily
    if not _table_exists(inspector, 'creator_daily'):
        op.create_table(
            'creator_daily',
            sa.Column('day', sa.Date(), nullable=False),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('pv', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('clicks', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('ctr', sa.Numeric(8, 6), nullable=False, server_default=sa.text('0')),
            sa.Column('price_median', sa.Numeric(10, 2), nullable=True),
            sa.Column('cpc_dynamic', sa.Numeric(10, 2), nullable=False, server_default=sa.text('0')),
            sa.Column('ppv', sa.Numeric(10, 4), nullable=False, server_default=sa.text('0')),
            sa.Column('ecmp', sa.Numeric(10, 2), nullable=False, server_default=sa.text('0')),
            sa.Column('payout_day', sa.Numeric(12, 2), nullable=False, server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
            sa.PrimaryKeyConstraint('day', 'user_id')
        )
        op.create_index('ix_creator_daily_user_day', 'creator_daily', ['user_id', 'day'])

    # creator_monthly
    if not _table_exists(inspector, 'creator_monthly'):
        op.create_table(
            'creator_monthly',
            sa.Column('month', sa.Date(), nullable=False),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('pv', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('clicks', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('payout_month', sa.Numeric(12, 2), nullable=False, server_default=sa.text('0')),
            sa.Column('closed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
            sa.PrimaryKeyConstraint('month', 'user_id')
        )
        op.create_index('ix_creator_monthly_user_month', 'creator_monthly', ['user_id', 'month'])

    # payout_ledger
    if not _table_exists(inspector, 'payout_ledger'):
        op.create_table(
            'payout_ledger',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('month', sa.Date(), nullable=False),
            sa.Column('confirmed_amount', sa.Numeric(12, 2), nullable=False, server_default=sa.text('0')),
            sa.Column('paid_amount', sa.Numeric(12, 2), nullable=False, server_default=sa.text('0')),
            sa.Column('unpaid_balance', sa.Numeric(12, 2), nullable=False, server_default=sa.text('0')),
            sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'unpaid'")),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
            sa.UniqueConstraint('user_id', 'month', name='uq_payout_ledger_user_month'),
            sa.CheckConstraint("status in ('unpaid','partially_paid','paid')", name='ck_payout_ledger_status'),
        )
        op.create_index('ix_payout_ledger_user_month', 'payout_ledger', ['user_id', 'month'])

    # payout_transactions
    if not _table_exists(inspector, 'payout_transactions'):
        op.create_table(
            'payout_transactions',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('requested_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('method', sa.String(length=64), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
        )
        op.create_index('ix_payout_transactions_user_paid_at', 'payout_transactions', ['user_id', 'paid_at'])

    # rate_overrides
    if not _table_exists(inspector, 'rate_overrides'):
        op.create_table(
            'rate_overrides',
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), primary_key=True),
            sa.Column('m_quality', sa.Numeric(4, 2), nullable=False, server_default=sa.text('1.0')),
            sa.Column('m_trust', sa.Numeric(4, 2), nullable=False, server_default=sa.text('1.0')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        )

    # event_log
    if not _table_exists(inspector, 'event_log'):
        op.create_table(
            'event_log',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('page_id', sa.BigInteger(), sa.ForeignKey('spots.id'), nullable=False),
            sa.Column('ota', sa.Text(), nullable=True),
            sa.Column('event_type', sa.String(length=16), nullable=False),
            sa.Column('client_key', sa.Text(), nullable=True),
            sa.Column('session_id', sa.Text(), nullable=True),
            sa.Column('user_agent', sa.Text(), nullable=True),
            sa.Column('ip', sa.dialects.postgresql.INET(), nullable=True),
            sa.Column('referrer', sa.Text(), nullable=True),
            sa.Column('dwell_ms', sa.Integer(), nullable=True),
            sa.Column('price_median', sa.Numeric(10, 2), nullable=True),
            sa.CheckConstraint("event_type in ('view','click')", name='ck_event_log_event_type'),
        )
        op.create_index('ix_event_log_user_created_at', 'event_log', ['user_id', 'created_at'])
        op.create_index('ix_event_log_event_type_created_at', 'event_log', ['event_type', 'created_at'])
        op.create_index('ix_event_log_user_page_event_created_at', 'event_log', ['user_id', 'page_id', 'event_type', 'created_at'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for name in ['event_log', 'rate_overrides', 'payout_transactions', 'payout_ledger', 'creator_monthly', 'creator_daily']:
        if _table_exists(inspector, name):
            op.drop_table(name)


