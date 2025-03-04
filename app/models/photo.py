from datetime import datetime
from app import db

class Photo(db.Model):
    __tablename__ = 'photos'
    
    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=False)
    photo_url = db.Column(db.Text, nullable=True)  # ユーザーアップロード写真用、nullableに変更
    google_photo_reference = db.Column(db.Text, nullable=True)  # Google写真参照用
    is_google_photo = db.Column(db.Boolean, default=False, nullable=False)  # 写真の種類を区別
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<Photo {self.id} for Spot {self.spot_id}>' 