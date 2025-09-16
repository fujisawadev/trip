from app import db, login_manager, bcrypt
from flask_login import UserMixin
from datetime import datetime, timedelta
import uuid
import re

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    bio = db.Column(db.String(500), nullable=True)
    profile_pic_url = db.Column(db.String(500), nullable=True)
    spots_heading = db.Column(db.String(100), nullable=True, default='おすすめスポット')
    slug = db.Column(db.String(100), unique=True, nullable=True)
    
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
    # アクセストークンの有効期限・リフレッシュ管理
    instagram_token_expires_at = db.Column(db.DateTime, nullable=True)
    instagram_token_last_refreshed_at = db.Column(db.DateTime, nullable=True)
    
    # Facebook連携情報
    facebook_token = db.Column(db.String(255), nullable=True)  # Facebook認証トークン
    facebook_page_id = db.Column(db.String(64), nullable=True)  # FacebookページID
    facebook_connected_at = db.Column(db.DateTime, nullable=True)  # Facebook連携日時
    webhook_subscription_id = db.Column(db.String(64), nullable=True)  # webhookサブスクリプションID
    
    # 自動返信設定
    autoreply_enabled = db.Column(db.Boolean, default=False)  # 有効/無効フラグ
    autoreply_template = db.Column(db.Text, nullable=True)  # 返信テンプレート
    autoreply_last_updated = db.Column(db.DateTime, nullable=True)  # 最終更新日時
    
    # アフィリエイト設定
    rakuten_affiliate_id = db.Column(db.String(100), nullable=True)  # 楽天アフィリエイトID
    
    # リレーションシップ
    spots = db.relationship('Spot', back_populates='user', lazy=True, cascade='all, delete-orphan')
    social_accounts = db.relationship('SocialAccount', back_populates='user', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, username, email, password=None, bio=None, profile_pic_url=None, spots_heading='おすすめスポット', slug=None):
        self.username = username
        self.email = email
        self.bio = bio
        self.profile_pic_url = profile_pic_url
        self.spots_heading = spots_heading
        self.slug = slug
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        # 自動返信のデフォルトテンプレートを設定
        self.autoreply_template = 'ご質問ありがとうございます！スポットの詳細はこちらのプロフィールページでご確認いただけます：{profile_url}'
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
    
    def generate_reset_token(self):
        return self.generate_reset_password_token()
    
    def generate_reset_password_token(self):
        self.reset_password_token = str(uuid.uuid4())
        self.reset_password_expires = datetime.utcnow() + timedelta(hours=24)
        return self.reset_password_token
        
    @classmethod
    def verify_reset_token(cls, token):
        """トークンを検証し、有効な場合はユーザーを返す"""
        if not token:
            return None
        
        user = cls.query.filter_by(reset_password_token=token).first()
        if not user or not user.reset_password_expires:
            return None
            
        # トークンの有効期限を確認
        if datetime.utcnow() > user.reset_password_expires:
            return None
            
        return user 
    
    @staticmethod
    def validate_slug(slug):
        """slug（URL）の検証
        - 英数字、ハイフン、アンダースコアのみ許可
        - 3~30文字の長さ制限
        - 予約語との衝突チェック
        """
        if not slug or len(slug) < 3 or len(slug) > 30:
            return False, "slugは3〜30文字にしてください"
            
        # 英数字、ハイフン、アンダースコアのみ許可
        if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
            return False, "slugに使用できるのは英数字、ハイフン(-)、アンダースコア(_)のみです"
            
        # 予約語チェック
        reserved_words = ['login', 'logout', 'signup', 'auth', 'admin', 'settings', 
                         'mypage', 'import', 'spot', 'api', 'static', 'upload', 
                         'profile', 'user', 'users', 'search', 'map', 'maps']
        if slug.lower() in reserved_words:
            return False, "このslugは使用できません"
            
        # 重複チェック
        if User.query.filter_by(slug=slug).first():
            return False, "このslugは既に使用されています"
            
        return True, "有効な表示名です"
    
    def get_public_url(self):
        """ユーザーの公開プロフィールURLを取得"""
        if self.slug:
            return f"/{self.slug}"
        return f"/{self.username}"