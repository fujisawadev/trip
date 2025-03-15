from datetime import datetime
from app import db
import json

class ImportHistory(db.Model):
    __tablename__ = 'import_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    source = db.Column(db.String(50), default='instagram', nullable=False)
    external_id = db.Column(db.String(255), nullable=True)  # Instagram投稿ID
    status = db.Column(db.String(20), nullable=False)  # 'success', 'skipped', 'failed'
    spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=True)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    raw_data = db.Column(db.JSON, nullable=True)  # 元の投稿データ
    error_message = db.Column(db.Text, nullable=True)  # エラーメッセージ
    
    # リレーションシップ
    user = db.relationship('User', backref=db.backref('import_history', lazy=True))
    spot = db.relationship('Spot', backref=db.backref('import_history', lazy=True))
    
    def __init__(self, user_id, source='instagram', external_id=None, status='pending', spot_id=None, raw_data=None, error_message=None):
        self.user_id = user_id
        self.source = source
        self.external_id = external_id
        self.status = status
        self.spot_id = spot_id
        self.raw_data = raw_data
        self.error_message = error_message
    
    def set_raw_data(self, data):
        """JSONデータを設定"""
        self.raw_data = data
    
    def get_raw_data(self):
        """JSONデータを取得"""
        return self.raw_data
    
    def __repr__(self):
        return f'<ImportHistory {self.id}: {self.source} {self.status}>' 