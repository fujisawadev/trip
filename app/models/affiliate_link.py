from datetime import datetime
from app import db

class AffiliateLink(db.Model):
    __tablename__ = 'affiliate_links'
    
    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=False)
    platform = db.Column(db.String(50), nullable=False)  # 'booking', 'rakuten', 'expedia'など
    url = db.Column(db.String(512), nullable=False)  # アフィリエイトリンクURL
    title = db.Column(db.String(100), nullable=True)  # 表示タイトル
    description = db.Column(db.String(255), nullable=True)  # 説明文
    logo_url = db.Column(db.String(255), nullable=True)  # ロゴURL
    icon_key = db.Column(db.String(50), nullable=True)  # SVGアイコンのキー（例: 'booking-com', 'rakuten-travel'）
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # リレーションシップ
    spot = db.relationship('Spot', backref='affiliate_links', lazy=True)
    
    def __repr__(self):
        return f'<AffiliateLink {self.platform} for Spot {self.spot_id}>' 