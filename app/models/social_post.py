from datetime import datetime
from app import db

class SocialPost(db.Model):
    __tablename__ = 'social_posts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=False)
    platform = db.Column(db.String(50), nullable=False)  # 'instagram', 'twitter', 'tiktok', 'youtube'
    post_url = db.Column(db.String(512), nullable=False)  # 投稿URL
    post_id = db.Column(db.String(255), nullable=True)  # プラットフォーム上の投稿ID
    thumbnail_url = db.Column(db.String(255), nullable=True)  # サムネイルURL
    caption = db.Column(db.Text, nullable=True)  # 投稿キャプション
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # リレーションシップ
    user = db.relationship('User', backref='social_posts', lazy=True)
    spot = db.relationship('Spot', backref='social_posts', lazy=True)
    
    def __repr__(self):
        return f'<SocialPost {self.platform} for Spot {self.spot_id} by User {self.user_id}>' 