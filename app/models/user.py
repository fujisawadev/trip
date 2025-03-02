from datetime import datetime
from flask_login import UserMixin
from app import db, login_manager, bcrypt

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    profile_pic_url = db.Column(db.String(255), nullable=True, default='default_profile.jpg')
    bio = db.Column(db.Text, nullable=True)
    spots_heading = db.Column(db.String(50), nullable=True, default='Favorite Spots')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # リレーションシップ
    spots = db.relationship('Spot', backref='user', lazy=True, cascade='all, delete-orphan')
    social_accounts = db.relationship('SocialAccount', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, username, email, password=None, bio=None, profile_pic_url=None, spots_heading='Favorite Spots'):
        self.username = username
        self.email = email
        if password:
            self.set_password(password)
        self.bio = bio
        if profile_pic_url:
            self.profile_pic_url = profile_pic_url
        self.spots_heading = spots_heading
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def __repr__(self):
        return f'<User {self.username}>' 