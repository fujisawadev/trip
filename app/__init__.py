import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# データベースの初期化
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    
    # アプリケーション設定
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app/app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'app/static/uploads')
    
    # 拡張機能の初期化
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    
    # ログイン設定
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'このページにアクセスするにはログインが必要です。'
    login_manager.login_message_category = 'info'
    
    # アップロードフォルダの作成
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # ルートの登録
    from app.routes import main, auth, spot, profile, public
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(spot.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(public.public_bp)
    
    return app 