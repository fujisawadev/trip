from datetime import datetime
from app import db

class SocialPost(db.Model):
    __tablename__ = 'social_posts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=False)
    platform = db.Column(db.String(50), nullable=False)  # 'instagram', 'twitter', 'tiktok', 'youtube'
    post_url = db.Column(db.String(2048), nullable=False)  # 投稿URL
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # リレーションシップ
    user = db.relationship('User', backref=db.backref('social_posts', lazy=True))
    spot = db.relationship('Spot', backref=db.backref('social_posts', lazy=True))
    
    def __repr__(self):
        return f'<SocialPost {self.platform} for Spot {self.spot_id} by User {self.user_id}>' 