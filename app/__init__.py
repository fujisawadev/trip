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
    # 環境変数を確認
    print(f"Starting application with environment: {os.environ.get('FLASK_ENV', 'production')}")
    
    # Flaskアプリケーションの設定
    app = Flask(__name__)
    
    # ロギングの設定を強化（特にHeroku環境向け）
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler()]
    )
    app.logger.setLevel(logging.INFO)
    app.logger.info("Application starting up with enhanced logging")
    
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
    
    # CSRFプロテクションの設定
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # デフォルトでは無効にし、必要なフォームで個別に有効化
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600 * 24  # 24時間有効（秒単位）
    
    # メールの初期化
    mail.init_app(app)
    
    # Instagram API設定
    app.config['INSTAGRAM_CLIENT_ID'] = os.environ.get('INSTAGRAM_CLIENT_ID')
    app.config['INSTAGRAM_CLIENT_SECRET'] = os.environ.get('INSTAGRAM_CLIENT_SECRET')
    app.config['INSTAGRAM_REDIRECT_URI'] = os.environ.get('INSTAGRAM_REDIRECT_URI')
    
    # Instagram Webhook設定
    app.config['INSTAGRAM_WEBHOOK_VERIFY_TOKEN'] = os.environ.get('INSTAGRAM_WEBHOOK_VERIFY_TOKEN')
    app.config['INSTAGRAM_APP_SECRET'] = os.environ.get('INSTAGRAM_APP_SECRET')
    
    # ベースURL設定
    app.config['BASE_URL'] = os.environ.get('BASE_URL', 'http://localhost:5000')
    
    # ルートの登録
    from app.routes import auth, main, profile, public, spot, api
    app.register_blueprint(auth.bp, url_prefix='/auth')
    app.register_blueprint(main.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(public.public_bp)
    app.register_blueprint(spot.bp)
    app.register_blueprint(api.api_bp)
    
    # 自動返信APIルートとWebhookルートの登録
    from app.routes.api.autoreply import autoreply_bp
    app.register_blueprint(autoreply_bp)
    
    from app.routes.api.webhook import webhook_bp
    app.register_blueprint(webhook_bp)
    
    return app 