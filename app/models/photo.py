from datetime import datetime
from app import db

class Photo(db.Model):
    __tablename__ = 'photos'
    
    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=False)
    photo_url = db.Column(db.Text, nullable=True)  # ユーザーアップロード写真用、nullableに変更
    is_google_photo = db.Column(db.Boolean, default=False, nullable=False)  # 写真の種類を区別
    is_primary = db.Column(db.Boolean, default=False, nullable=False)  # プライマリ写真かどうか
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<Photo {self.id} for Spot {self.spot_id}>' 

    def to_dict(self):
        """Photoオブジェクトを辞書に変換する"""
        return {
            'id': self.id,
            'spot_id': self.spot_id,
            'photo_url': self.photo_url,
            'is_primary': self.is_primary,
            'created_at': self.created_at.isoformat()
        } 