from datetime import datetime
from app import db

class ImportProgress(db.Model):
    __tablename__ = 'import_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    source = db.Column(db.String(50), default='instagram', nullable=False)
    
    # Import job status tracking
    job_id = db.Column(db.String(36), unique=True, nullable=True) # UUID for the job
    status = db.Column(db.String(20), default='pending', nullable=False) # e.g., pending, processing, completed, failed
    result_data = db.Column(db.Text, nullable=True) # JSON results for successful jobs
    error_info = db.Column(db.Text, nullable=True) # Error message for failed jobs

    # Save job status tracking
    save_job_id = db.Column(db.String(36), nullable=True) # UUID for the save job
    save_status = db.Column(db.String(20), nullable=True) # e.g., pending, processing, completed, failed
    save_result_data = db.Column(db.Text, nullable=True) # JSON results for successful save jobs
    save_error_info = db.Column(db.Text, nullable=True) # Error message for failed save jobs

    last_imported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_post_id = db.Column(db.String(255), nullable=True)
    last_post_timestamp = db.Column(db.DateTime, nullable=True)
    next_page_cursor = db.Column(db.String(255), nullable=True)
    total_imported_count = db.Column(db.Integer, default=0, nullable=False)
    
    # 期間指定関連のカラムを追加
    import_period_start = db.Column(db.DateTime, nullable=True)
    import_period_end = db.Column(db.DateTime, nullable=True)
    
    # リレーションシップ
    user = db.relationship('User', backref=db.backref('import_progress', lazy=True))
    
    # ユニーク制約（ユーザーとソースの組み合わせで1レコードのみ）
    __table_args__ = (
        db.UniqueConstraint('user_id', 'source', name='uix_import_progress_user_source'),
    )
    
    def __repr__(self):
        return f'<ImportProgress {self.id}: {self.source} {self.total_imported_count}件>' 