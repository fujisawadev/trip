from datetime import datetime, timedelta
import secrets
from flask_login import UserMixin
from app import db, login_manager, bcrypt

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    bio = db.Column(db.Text, nullable=True)
    profile_pic_url = db.Column(db.String(255), nullable=True)
    spots_heading = db.Column(db.String(100), default="My Spots")
    
    # パスワードリセット用のフィールド
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires_at = db.Column(db.DateTime, nullable=True)
    
    # SNS連携用のフィールド
    instagram_token = db.Column(db.String(255), nullable=True)
    instagram_user_id = db.Column(db.String(64), nullable=True)
    instagram_username = db.Column(db.String(64), nullable=True)
    instagram_connected_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # リレーションシップ - backrefの代わりにback_populatesを使用
    spots = db.relationship('Spot', back_populates='user', lazy=True, cascade='all, delete-orphan')
    social_accounts = db.relationship('SocialAccount', back_populates='user', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, username, email, password=None, bio=None, profile_pic_url=None, spots_heading='Favorite Spots'):
        self.username = username
        self.email = email
        if password:
            self.set_password(password)
        self.bio = bio
        if profile_pic_url:
            self.profile_pic_url = profile_pic_url
        self.spots_heading = spots_heading
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def generate_reset_token(self):
        """パスワードリセット用のトークンを生成する"""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires_at = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        return self.reset_token
    
    def verify_reset_token(self, token):
        """パスワードリセット用のトークンを検証する"""
        if self.reset_token != token:
            return False
        if self.reset_token_expires_at < datetime.utcnow():
            return False
        return True
    
    def clear_reset_token(self):
        """パスワードリセット用のトークンをクリアする"""
        self.reset_token = None
        self.reset_token_expires_at = None
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.username}>' 