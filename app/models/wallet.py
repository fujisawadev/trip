from datetime import datetime
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from app import db


class CreatorDaily(db.Model):
    __tablename__ = 'creator_daily'

    day = db.Column(db.Date, nullable=False, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False, primary_key=True)

    pv = db.Column(db.Integer, nullable=False, default=0)
    clicks = db.Column(db.Integer, nullable=False, default=0)
    ctr = db.Column(db.Numeric(8, 6), nullable=False, default=0)
    price_median = db.Column(db.Numeric(10, 2), nullable=True)
    cpc_dynamic = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    ppv = db.Column(db.Numeric(10, 4), nullable=False, default=0)
    ecmp = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    payout_day = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index('ix_creator_daily_user_day', 'user_id', 'day'),
    )


class CreatorMonthly(db.Model):
    __tablename__ = 'creator_monthly'

    month = db.Column(db.Date, nullable=False, primary_key=True)  # 月初
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False, primary_key=True)

    pv = db.Column(db.Integer, nullable=False, default=0)
    clicks = db.Column(db.Integer, nullable=False, default=0)
    payout_month = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_creator_monthly_user_month', 'user_id', 'month'),
    )


class PayoutLedger(db.Model):
    __tablename__ = 'payout_ledger'

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False)
    month = db.Column(db.Date, nullable=False)  # 締め月

    confirmed_amount = db.Column(db.Numeric(12, 2), nullable=False)
    paid_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    unpaid_balance = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(32), nullable=False, default='unpaid')  # 'unpaid' | 'partially_paid' | 'paid'
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('user_id', 'month', name='uq_payout_ledger_user_month'),
        CheckConstraint("status in ('unpaid','partially_paid','paid')", name='ck_payout_ledger_status'),
        Index('ix_payout_ledger_user_month', 'user_id', 'month'),
    )


class PayoutTransaction(db.Model):
    __tablename__ = 'payout_transactions'

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False)
    requested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(64), nullable=True)
    note = db.Column(db.Text, nullable=True)

    __table_args__ = (
        Index('ix_payout_transactions_user_paid_at', 'user_id', 'paid_at'),
    )


class RateOverride(db.Model):
    __tablename__ = 'rate_overrides'

    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), primary_key=True)
    m_quality = db.Column(db.Numeric(4, 2), nullable=False, default=1.0)
    m_trust = db.Column(db.Numeric(4, 2), nullable=False, default=1.0)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)


