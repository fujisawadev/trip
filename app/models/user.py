from app import db, login_manager, bcrypt
from flask_login import UserMixin
from datetime import datetime, timedelta
import uuid

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=True, index=True, unique=True)
    email = db.Column(db.String(120), nullable=True, index=True, unique=True)
    password_hash = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    bio = db.Column(db.Text, nullable=True)
    profile_pic_url = db.Column(db.String(255), nullable=True)
    spots_heading = db.Column(db.String(100), nullable=True, default='Favorite Spots')
    
    # アカウント検証
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(64), nullable=True)
    verification_sent_at = db.Column(db.DateTime, nullable=True)
    
    # パスワードリセット
    reset_password_token = db.Column(db.String(100), nullable=True)
    reset_password_expires = db.Column(db.DateTime, nullable=True)
    
    # Instagram連携情報
    instagram_token = db.Column(db.String(255), nullable=True)
    instagram_user_id = db.Column(db.String(64), nullable=True)
    instagram_username = db.Column(db.String(64), nullable=True)
    instagram_connected_at = db.Column(db.DateTime, nullable=True)
    instagram_business_id = db.Column(db.String(64), nullable=True)  # InstagramビジネスアカウントID
    
    # Facebook連携情報
    facebook_token = db.Column(db.String(255), nullable=True)  # Facebook認証トークン
    facebook_page_id = db.Column(db.String(64), nullable=True)  # FacebookページID
    facebook_connected_at = db.Column(db.DateTime, nullable=True)  # Facebook連携日時
    webhook_subscription_id = db.Column(db.String(64), nullable=True)  # webhookサブスクリプションID
    
    # 自動返信設定
    autoreply_enabled = db.Column(db.Boolean, default=False)  # 有効/無効フラグ
    autoreply_template = db.Column(db.Text, nullable=True)  # 返信テンプレート
    autoreply_last_updated = db.Column(db.DateTime, nullable=True)  # 最終更新日時
    
    # 追加設定
    website = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    
    # リレーションシップ
    spots = db.relationship('Spot', back_populates='user', lazy=True, cascade='all, delete-orphan')
    social_accounts = db.relationship('SocialAccount', back_populates='user', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, username, email, password=None, bio=None, profile_pic_url=None, spots_heading='Favorite Spots'):
        self.username = username
        self.email = email
        self.bio = bio
        self.profile_pic_url = profile_pic_url
        self.spots_heading = spots_heading
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        if password:
            self.set_password(password)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        if self.password_hash:
            return bcrypt.check_password_hash(self.password_hash, password)
        return False
    
    def generate_verification_token(self):
        self.verification_token = str(uuid.uuid4())
        self.verification_sent_at = datetime.utcnow()
        return self.verification_token
    
    def generate_reset_password_token(self):
        self.reset_password_token = str(uuid.uuid4())
        self.reset_password_expires = datetime.utcnow() + timedelta(hours=24)
        return self.reset_password_token 