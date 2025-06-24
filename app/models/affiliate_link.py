from datetime import datetime
from app import db

class AffiliateLink(db.Model):
    __tablename__ = 'affiliate_links'
    
    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=False)
    platform = db.Column(db.String(50), nullable=False)  # 'booking', 'rakuten', 'expedia'など
    url = db.Column(db.Text, nullable=False)  # アフィリエイトリンクURL
    title = db.Column(db.Text, nullable=True)  # 表示タイトル
    description = db.Column(db.Text, nullable=True)  # 説明文
    logo_url = db.Column(db.Text, nullable=True)  # ロゴURL
    icon_key = db.Column(db.String(50), nullable=True)  # SVGアイコンのキー（例: 'booking-com', 'rakuten-travel'）
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # リレーションシップ
    spot = db.relationship('Spot', backref='affiliate_links', lazy=True)
    
    def __repr__(self):
        return f'<AffiliateLink {self.platform} for Spot {self.spot_id}>'
    
    def to_dict(self):
        """AffiliateLink オブジェクトを辞書に変換する"""
        return {
            'id': self.id,
            'spot_id': self.spot_id,
            'platform': self.platform,
            'url': self.url,
            'title': self.title,
            'description': self.description,
            'logo_url': self.logo_url,
            'icon_key': self.icon_key,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        } 