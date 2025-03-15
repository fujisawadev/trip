import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# データベースの初期化
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()
mail = Mail()

def create_app(config_class=None):
    """アプリケーションファクトリ"""
    app = Flask(__name__)
    
    # 設定の読み込み
    if config_class is None:
        from app.config import Config
        app.config.from_object(Config)
    else:
        app.config.from_object(config_class)
    
    # データベースの初期化
    db.init_app(app)
    migrate.init_app(app, db)
    
    # ログイン管理の初期化
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'このページにアクセスするにはログインが必要です。'
    login_manager.login_message_category = 'info'
    
    # CSRFプロテクションの初期化
    csrf.init_app(app)
    
    # CSRFトークンをアプリケーションで利用可能にする
    app.csrf = csrf
    
    # メールの初期化
    mail.init_app(app)
    
    # Instagram API設定
    app.config['INSTAGRAM_CLIENT_ID'] = os.environ.get('INSTAGRAM_CLIENT_ID')
    app.config['INSTAGRAM_CLIENT_SECRET'] = os.environ.get('INSTAGRAM_CLIENT_SECRET')
    app.config['INSTAGRAM_REDIRECT_URI'] = os.environ.get('INSTAGRAM_REDIRECT_URI')
    
    # ルートの登録
    from app.routes import auth, main, profile, public, spot, api
    app.register_blueprint(auth.bp, url_prefix='/auth')
    app.register_blueprint(main.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(public.public_bp)
    app.register_blueprint(spot.bp)
    app.register_blueprint(api.api_bp)
    
    return app 