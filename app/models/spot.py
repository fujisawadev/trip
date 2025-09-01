from datetime import datetime
from app import db

class Spot(db.Model):
    __tablename__ = 'spots'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 地図情報用のフィールドを追加
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    # Google Places API関連のフィールド
    google_place_id = db.Column(db.Text, nullable=True)
    formatted_address = db.Column(db.Text, nullable=True)
    types = db.Column(db.Text, nullable=True)  # JSON形式で保存
    thumbnail_url = db.Column(db.Text, nullable=True)
    summary_location = db.Column(db.Text, nullable=True)  # サマリーロケーション（国、都道府県、市区町村）
    google_maps_url = db.Column(db.Text, nullable=True)  # Google Mapsへの直接リンク
    
    
    # レビュー関連のフィールド
    rating = db.Column(db.Float, nullable=False, default=0.0)  # 評価の平均点（1.0-5.0）
    review_count = db.Column(db.Integer, default=0, nullable=False)  # レビュー数
    review_summary = db.Column(db.Text, nullable=True)  # Googleレビューの要約テキスト
    
    # カスタムリンク（任意の外部サイトを1件だけ持たせる）
    custom_link_title = db.Column(db.Text, nullable=True)
    custom_link_url = db.Column(db.Text, nullable=True)
    
    # リレーションシップ
    photos = db.relationship('Photo', backref='spot', lazy=True, cascade='all, delete-orphan')
    user = db.relationship('User', back_populates='spots', foreign_keys=[user_id], lazy=True)
    
    def __repr__(self):
        return f'<Spot {self.name}>'

    def to_dict(self):
        """Spotオブジェクトを辞書に変換する"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'location': self.location,
            'category': self.category,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'latitude': self.latitude,
            'longitude': self.longitude,
            'google_place_id': self.google_place_id,
            'formatted_address': self.formatted_address,
            'types': self.types,
            'thumbnail_url': self.thumbnail_url,
            'summary_location': self.summary_location,
            'google_maps_url': self.google_maps_url,
            'rating': self.rating,
            'review_count': self.review_count,
            'review_summary': self.review_summary,
            'photos': [photo.to_dict() for photo in self.photos]
        }