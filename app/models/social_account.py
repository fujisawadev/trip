from datetime import datetime
from app import db

class SocialAccount(db.Model):
    __tablename__ = 'social_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # SNSプラットフォーム用のフィールド
    instagram = db.Column(db.String(255), nullable=True)
    twitter = db.Column(db.String(255), nullable=True)
    tiktok = db.Column(db.String(255), nullable=True)
    youtube = db.Column(db.String(255), nullable=True)
    
    # OAuth用のフィールド（将来的に使用する可能性がある）
    platform = db.Column(db.String(50), nullable=True)  # 'instagram', 'facebook', 'linkedin'など
    account_id = db.Column(db.String(255), nullable=True)
    access_token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SocialAccount for User {self.user_id}>' 