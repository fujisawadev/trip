from datetime import datetime, timedelta
import uuid
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # アカウント設定
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    
    # プロフィール情報
    display_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(200))
    
    # Instagram連携情報
    instagram_token = db.Column(db.String(500))
    instagram_business_id = db.Column(db.String(100))
    instagram_username = db.Column(db.String(100))
    
    # Facebook連携情報（後方互換性のため）
    facebook_token = db.Column(db.String(500))
    facebook_page_id = db.Column(db.String(100))
    
    # 自動返信設定
    autoreply_enabled = db.Column(db.Boolean, default=False)
    autoreply_template = db.Column(db.Text, default="ご質問ありがとうございます。より詳しい情報は私のプロフィールをご覧ください: {profile_url}")
    
    # アカウント検証
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), nullable=True)
    verification_sent_at = db.Column(db.DateTime, nullable=True)
    
    # パスワードリセット
    reset_password_token = db.Column(db.String(100), nullable=True)
    reset_password_expires = db.Column(db.DateTime, nullable=True)
    
    # 追加設定
    settings = db.Column(db.JSON, nullable=True, default={})
    preferences = db.Column(db.JSON, nullable=True, default={})
    
    # リレーションシップ
    trips = db.relationship('Trip', backref='user', lazy=True)
    locations = db.relationship('Location', backref='user', lazy=True)
    
    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password = generate_password_hash(password)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def check_password(self, password):
        return check_password_hash(self.password, password)
    
    def generate_verification_token(self):
        self.verification_token = str(uuid.uuid4())
        self.verification_sent_at = datetime.utcnow()
        return self.verification_token
    
    def verify_email(self):
        self.is_verified = True
        self.verification_token = None
        return True
    
    def generate_reset_token(self):
        self.reset_password_token = str(uuid.uuid4())
        self.reset_password_expires = datetime.utcnow() + timedelta(hours=24)
        return self.reset_password_token
    
    def is_instagram_connected(self):
        """Instagramに接続されているかを確認"""
        return bool(self.instagram_token and self.instagram_business_id)
    
    # 必要なメソッドや追加のプロパティをここに定義
    # ... 