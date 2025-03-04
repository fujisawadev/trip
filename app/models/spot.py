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
    google_photo_reference = db.Column(db.Text, nullable=True)  # Google写真参照情報
    summary_location = db.Column(db.Text, nullable=True)  # サマリーロケーション（国、都道府県、市区町村）
    google_maps_url = db.Column(db.Text, nullable=True)  # Google Mapsへの直接リンク
    
    # リレーションシップ
    photos = db.relationship('Photo', backref='spot', lazy=True, cascade='all, delete-orphan')
    user = db.relationship('User', back_populates='spots', foreign_keys=[user_id], lazy=True)
    
    def __repr__(self):
        return f'<Spot {self.name}>'