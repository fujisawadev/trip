from datetime import datetime
from sqlalchemy import Index, CheckConstraint
from sqlalchemy.dialects.postgresql import INET
from app import db


class EventLog(db.Model):
    __tablename__ = 'event_log'

    id = db.Column(db.BigInteger, primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # クリエイター（=既存ユーザー）と対象ページ（v1はスポット詳細のみ）
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)
    page_id = db.Column(db.BigInteger, db.ForeignKey('spots.id', ondelete='SET NULL'), nullable=True, index=True)

    # OTA プラットフォーム識別（例: 'rakuten', 'jalan', 'booking', 'agoda', 'expedia', 'yahoo'）
    ota = db.Column(db.Text, nullable=True)

    # 'view' | 'click'
    event_type = db.Column(db.String(16), nullable=False)

    # 匿名化識別子（保存はHMAC済みの client_key のみ）とセッション
    client_key = db.Column(db.Text, nullable=True)
    session_id = db.Column(db.Text, nullable=True)

    # コンテキスト
    user_agent = db.Column(db.Text, nullable=True)
    ip = db.Column(INET, nullable=True)
    referrer = db.Column(db.Text, nullable=True)

    # view 専用
    dwell_ms = db.Column(db.Integer, nullable=True)
    price_median = db.Column(db.Numeric(10, 2), nullable=True)

    # Bot 判定（保存時の軽量フラグ）
    is_bot = db.Column(db.Boolean, nullable=False, default=False)
    bot_reason = db.Column(db.Text, nullable=True)

    # リレーション（必要最小限。backref は既存側未定義なので宣言のみ）
    user = db.relationship('User', primaryjoin='EventLog.user_id == User.id', lazy=True)
    page = db.relationship('Spot', primaryjoin='EventLog.page_id == Spot.id', lazy=True, passive_deletes=True)

    __table_args__ = (
        # event_type の簡易チェック
        CheckConstraint("event_type in ('view','click')", name='ck_event_log_event_type'),
        # よく使うクエリ用の複合インデックス
        Index('ix_event_log_user_created_at', 'user_id', 'created_at'),
        Index('ix_event_log_event_type_created_at', 'event_type', 'created_at'),
        Index('ix_event_log_user_page_event_created_at', 'user_id', 'page_id', 'event_type', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<EventLog id={self.id} user_id={self.user_id} page_id={self.page_id} type={self.event_type}>"


