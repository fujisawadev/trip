from datetime import datetime
from app import db

class ImportProgress(db.Model):
    __tablename__ = 'import_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    source = db.Column(db.String(50), default='instagram', nullable=False)
    last_imported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_post_id = db.Column(db.String(255), nullable=True)
    last_post_timestamp = db.Column(db.DateTime, nullable=True)
    next_page_cursor = db.Column(db.String(255), nullable=True)
    total_imported_count = db.Column(db.Integer, default=0, nullable=False)
    
    # リレーションシップ
    user = db.relationship('User', backref=db.backref('import_progress', lazy=True))
    
    # ユニーク制約（ユーザーとソースの組み合わせで1レコードのみ）
    __table_args__ = (
        db.UniqueConstraint('user_id', 'source', name='uix_import_progress_user_source'),
    )
    
    def __init__(self, user_id, source='instagram'):
        self.user_id = user_id
        self.source = source
        self.last_imported_at = datetime.utcnow()
        self.total_imported_count = 0
        
    def __repr__(self):
        return f'<ImportProgress {self.id}: {self.source} {self.total_imported_count}件>' 