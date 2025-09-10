from datetime import datetime
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from app import db


class StripeAccount(db.Model):
    __tablename__ = 'stripe_accounts'

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)

    stripe_account_id = db.Column(db.String(255), nullable=False, unique=True)
    status = db.Column(db.String(32), nullable=False, default='created')  # created | onboarding | verified | restricted
    payouts_enabled = db.Column(db.Boolean, nullable=False, default=False)
    charges_enabled = db.Column(db.Boolean, nullable=False, default=False)
    requirements_json = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_stripe_accounts_user_id', 'user_id'),
    )


class Withdrawal(db.Model):
    __tablename__ = 'withdrawals'

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(32), nullable=False, default='requested')
    # requested | pending_review | approved | transferring | payout_pending | paid | failed | canceled
    review_required = db.Column(db.Boolean, nullable=False, default=False)
    reason = db.Column(db.Text, nullable=True)
    idempotency_key = db.Column(db.String(255), nullable=True, unique=True)

    requested_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    cooldown_until_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('ix_withdrawals_user_status', 'user_id', 'status'),
        CheckConstraint("status in ('requested','pending_review','approved','transferring','payout_pending','paid','failed','canceled')",
                        name='ck_withdrawals_status')
    )


class Transfer(db.Model):
    __tablename__ = 'transfers'

    id = db.Column(db.BigInteger, primary_key=True)
    withdrawal_id = db.Column(db.BigInteger, db.ForeignKey('withdrawals.id'), nullable=False, index=True)

    stripe_transfer_id = db.Column(db.String(255), nullable=True, unique=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(32), nullable=False, default='created')  # created | failed
    error_code = db.Column(db.String(64), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index('ix_transfers_withdrawal_id', 'withdrawal_id'),
        CheckConstraint("status in ('created','failed')", name='ck_transfers_status')
    )


class Payout(db.Model):
    __tablename__ = 'payouts'

    id = db.Column(db.BigInteger, primary_key=True)
    withdrawal_id = db.Column(db.BigInteger, db.ForeignKey('withdrawals.id'), nullable=False, index=True)

    stripe_payout_id = db.Column(db.String(255), nullable=True, unique=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(32), nullable=False, default='created')  # created | paid | failed | canceled
    failure_code = db.Column(db.String(64), nullable=True)
    failure_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('ix_payouts_withdrawal_id', 'withdrawal_id'),
        CheckConstraint("status in ('created','paid','failed','canceled')", name='ck_payouts_status')
    )


class LedgerEntry(db.Model):
    __tablename__ = 'ledger_entries'

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)

    entry_type = db.Column(db.String(64), nullable=False)  # withdrawal_hold, withdrawal_release, payout_paid など
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    dr_cr = db.Column(db.String(2), nullable=False)  # DR or CR

    ref_type = db.Column(db.String(64), nullable=True)  # 'withdrawal' | 'transfer' | 'payout'
    ref_id = db.Column(db.BigInteger, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ledger_entries_user_created', 'user_id', 'created_at'),
        CheckConstraint("dr_cr in ('DR','CR')", name='ck_ledger_entries_drcr')
    )


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.BigInteger, primary_key=True)
    actor = db.Column(db.String(64), nullable=False)  # user:{id} | system | admin:{id}
    action = db.Column(db.String(64), nullable=False)
    payload_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index('ix_audit_logs_actor_created', 'actor', 'created_at'),
    )


