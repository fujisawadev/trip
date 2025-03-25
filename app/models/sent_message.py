from app import db
from datetime import datetime, timedelta

class SentMessage(db.Model):
    """送信済みメッセージを記録するモデル
    
    このモデルは自動返信により送信されたメッセージを記録し、
    同一ユーザーへの重複送信や無限ループを防止するために使用されます。
    """
    __tablename__ = 'sent_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(255), nullable=False, index=True)  # Instagramのmid
    sender_id = db.Column(db.String(255), nullable=False, index=True)   # 送信者ID
    recipient_id = db.Column(db.String(255), nullable=False, index=True)  # 受信者ID
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # メッセージの有効期限
    
    # インデックスを追加して検索を高速化
    __table_args__ = (
        db.Index('idx_sender_recipient', 'sender_id', 'recipient_id'),
    )
    
    def __init__(self, message_id, sender_id, recipient_id, expires_hours=24):
        self.message_id = message_id
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.sent_at = datetime.utcnow()
        self.expires_at = self.sent_at + timedelta(hours=expires_hours)
    
    @classmethod
    def cleanup_expired(cls):
        """期限切れのメッセージレコードを削除する"""
        now = datetime.utcnow()
        expired = cls.query.filter(cls.expires_at < now).all()
        for record in expired:
            db.session.delete(record)
        db.session.commit()
        return len(expired)
    
    @classmethod
    def has_recent_message(cls, sender_id, recipient_id):
        """特定の送信者と受信者の組み合わせで最近送信されたメッセージがあるか確認する"""
        now = datetime.utcnow()
        return cls.query.filter(
            cls.sender_id == sender_id,
            cls.recipient_id == recipient_id,
            cls.expires_at > now
        ).first() is not None 