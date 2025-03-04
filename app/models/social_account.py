from datetime import datetime
from app import db

class SocialAccount(db.Model):
    __tablename__ = 'social_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # SNSプラットフォーム用のフィールド
    instagram = db.Column(db.Text, nullable=True)
    twitter = db.Column(db.Text, nullable=True)
    tiktok = db.Column(db.Text, nullable=True)
    youtube = db.Column(db.Text, nullable=True)
    
    # OAuth用のフィールド（将来的に使用する可能性がある）
    platform = db.Column(db.String(50), nullable=False)  # 'instagram', 'twitter', 'tiktok', 'youtube'
    account_id = db.Column(db.Text, nullable=True)
    access_token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    
    username = db.Column(db.String(100), nullable=False)
    profile_url = db.Column(db.Text, nullable=False)  # プロフィールURL
    icon_key = db.Column(db.String(50), nullable=True)  # SVGアイコンのキー（例: 'instagram', 'twitter'）
    display_order = db.Column(db.Integer, default=0, nullable=False)  # 表示順序
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # リレーションシップ
    user = db.relationship('User', back_populates='social_accounts', foreign_keys=[user_id], lazy=True)
    
    def __repr__(self):
        return f'<SocialAccount {self.platform} for User {self.user_id}>' 