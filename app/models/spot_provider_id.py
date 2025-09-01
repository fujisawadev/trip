from datetime import datetime
from app import db


class SpotProviderId(db.Model):
    __tablename__ = 'spot_provider_ids'

    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)  # 'agoda', 'rakuten', 'expedia' など
    external_id = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    spot = db.relationship('Spot', backref=db.backref('provider_ids', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f"<SpotProviderId spot={self.spot_id} provider={self.provider} external_id={self.external_id}>"

    def to_dict(self):
        return {
            'id': self.id,
            'spot_id': self.spot_id,
            'provider': self.provider,
            'external_id': self.external_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


