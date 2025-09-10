"""add stripe/wallet payout tables (idempotent)

Revision ID: 5d2a1c3b9e77
Revises: ed7a33d3f886
Create Date: 2025-09-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5d2a1c3b9e77'
down_revision = 'ed7a33d3f886'
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

    # stripe_accounts
    if not _table_exists(inspector, 'stripe_accounts'):
        op.create_table(
            'stripe_accounts',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('stripe_account_id', sa.String(length=255), nullable=False, unique=True),
            sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'created'")),
            sa.Column('payouts_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('charges_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('requirements_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        )
        op.create_index('ix_stripe_accounts_user_id', 'stripe_accounts', ['user_id'])

    # withdrawals
    if not _table_exists(inspector, 'withdrawals'):
        op.create_table(
            'withdrawals',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'requested'")),
            sa.Column('review_required', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('idempotency_key', sa.String(length=255), nullable=True, unique=True),
            sa.Column('requested_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
            sa.Column('cooldown_until_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_withdrawals_user_status', 'withdrawals', ['user_id', 'status'])
        op.create_check_constraint('ck_withdrawals_status', 'withdrawals',
                                   "status in ('requested','pending_review','approved','transferring','payout_pending','paid','failed','canceled')")

    # transfers
    if not _table_exists(inspector, 'transfers'):
        op.create_table(
            'transfers',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('withdrawal_id', sa.BigInteger(), sa.ForeignKey('withdrawals.id'), nullable=False),
            sa.Column('stripe_transfer_id', sa.String(length=255), nullable=True, unique=True),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'created'")),
            sa.Column('error_code', sa.String(length=64), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        )
        op.create_index('ix_transfers_withdrawal_id', 'transfers', ['withdrawal_id'])
        op.create_check_constraint('ck_transfers_status', 'transfers', "status in ('created','failed')")

    # payouts
    if not _table_exists(inspector, 'payouts'):
        op.create_table(
            'payouts',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('withdrawal_id', sa.BigInteger(), sa.ForeignKey('withdrawals.id'), nullable=False),
            sa.Column('stripe_payout_id', sa.String(length=255), nullable=True, unique=True),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'created'")),
            sa.Column('failure_code', sa.String(length=64), nullable=True),
            sa.Column('failure_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
            sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_payouts_withdrawal_id', 'payouts', ['withdrawal_id'])
        op.create_check_constraint('ck_payouts_status', 'payouts', "status in ('created','paid','failed','canceled')")

    # ledger_entries
    if not _table_exists(inspector, 'ledger_entries'):
        op.create_table(
            'ledger_entries',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('entry_type', sa.String(length=64), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('dr_cr', sa.String(length=2), nullable=False),
            sa.Column('ref_type', sa.String(length=64), nullable=True),
            sa.Column('ref_id', sa.BigInteger(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        )
        op.create_index('ix_ledger_entries_user_created', 'ledger_entries', ['user_id', 'created_at'])
        op.create_check_constraint('ck_ledger_entries_drcr', 'ledger_entries', "dr_cr in ('DR','CR')")

    # audit_logs
    if not _table_exists(inspector, 'audit_logs'):
        op.create_table(
            'audit_logs',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('actor', sa.String(length=64), nullable=False),
            sa.Column('action', sa.String(length=64), nullable=False),
            sa.Column('payload_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')),
        )
        op.create_index('ix_audit_logs_actor_created', 'audit_logs', ['actor', 'created_at'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for name in ['audit_logs', 'ledger_entries', 'payouts', 'transfers', 'withdrawals', 'stripe_accounts']:
        if _table_exists(inspector, name):
            op.drop_table(name)



