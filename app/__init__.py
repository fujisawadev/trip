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

def create_app(test_config=None):
    # アプリケーションの作成と設定
    app = Flask(__name__, instance_relative_config=True)
    
    # 設定の読み込み
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(app.instance_path, 'app.db')),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.path.join(app.static_folder, 'uploads'),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16MB max upload
    )
    
    # PostgreSQL固有の設定
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_size': 10,
            'pool_recycle': 3600,
            'pool_pre_ping': True
        }
    
    if test_config is not None:
        # テスト用の設定を上書き
        app.config.from_mapping(test_config)
    
    # データベースの初期化
    db.init_app(app)
    migrate.init_app(app, db)
    
    # ログイン管理の初期化
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'ログインしてください。'
    login_manager.login_message_category = 'info'
    
    # CSRFプロテクションの初期化
    csrf.init_app(app)
    
    # アップロードディレクトリの作成
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # ルートの登録
    from app.routes import main, auth, profile, public, spot, api
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(public.public_bp)
    app.register_blueprint(spot.bp)
    app.register_blueprint(api.api_bp)
    
    # APIルートのCSRF保護を無効化
    csrf.exempt(api.api_bp)
    
    return app 