import os
from flask import Flask, render_template, redirect, request
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
    flask_app = Flask(__name__)
    
    # www サブドメインから非www へのリダイレクトミドルウェア
    @flask_app.before_request
    def redirect_www_to_non_www():
        # 本番環境で、かつホストがwww.my-map.linkの場合
        if request.host.startswith('www.my-map.link'):
            url_parts = list(request.url.partition('://'))
            url_parts[1] = '://'
            url_parts[2] = url_parts[2].replace('www.my-map.link', 'my-map.link', 1)
            return redirect('https' + url_parts[1] + url_parts[2], code=301)
    
    # CSRF保護の設定 - テスト用に一時的に無効化
    flask_app.config['WTF_CSRF_ENABLED'] = False  # CSRF保護を無効化
    
    # ロギングの設定を強化（特にHeroku環境向け）
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler()]
    )
    flask_app.logger.setLevel(logging.INFO)
    flask_app.logger.info("Application starting up with enhanced logging")
    
    # 設定の読み込み
    if config_class is None:
        from app.config import Config
        flask_app.config.from_object(Config)
    else:
        flask_app.config.from_object(config_class)
    
    # データベースの初期化
    db.init_app(flask_app)
    migrate.init_app(flask_app, db)
    
    # エラーハンドリングのセットアップ - トランザクションのアボート状態をリセットする
    @flask_app.teardown_request
    def teardown_request(exception=None):
        if exception:
            db.session.rollback()
            flask_app.logger.warning(f"リクエスト中に例外が発生したためセッションをロールバックします: {str(exception)}")
        db.session.remove()

    # ログイン管理の初期化
    login_manager.init_app(flask_app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'このページにアクセスするにはログインが必要です。'
    login_manager.login_message_category = 'info'
    
    # CSRFプロテクションの初期化（APIエンドポイントを除外）
    csrf.init_app(flask_app)
    flask_app.csrf = csrf
    
    # メールの初期化
    mail.init_app(flask_app)
    
    # Google Maps APIキーの設定
    flask_app.config['GOOGLE_MAPS_API_KEY'] = os.environ.get('GOOGLE_MAPS_API_KEY')
    
    # Instagram API設定
    flask_app.config['INSTAGRAM_CLIENT_ID'] = os.environ.get('INSTAGRAM_CLIENT_ID')
    flask_app.config['INSTAGRAM_CLIENT_SECRET'] = os.environ.get('INSTAGRAM_CLIENT_SECRET')
    flask_app.config['INSTAGRAM_REDIRECT_URI'] = os.environ.get('INSTAGRAM_REDIRECT_URI')
    
    # Instagram Webhook設定
    flask_app.config['INSTAGRAM_WEBHOOK_VERIFY_TOKEN'] = os.environ.get('INSTAGRAM_WEBHOOK_VERIFY_TOKEN', 'instagram_webhook_verify_token')
    flask_app.config['INSTAGRAM_APP_SECRET'] = os.environ.get('INSTAGRAM_APP_SECRET')
    
    # ベースURL設定
    flask_app.config['BASE_URL'] = os.environ.get('BASE_URL', 'http://localhost:5000')
    
    # ルートの登録 - 各ブループリントを個別にインポート
    from app.routes.auth import bp as auth_bp
    from app.routes.main import bp as main_bp
    from app.routes.profile import bp as profile_bp
    from app.routes.public import public_bp
    from app.routes.spot import bp as spot_bp
    
    # API関連のブループリント
    from app.routes.api import url_api_bp  # URL検証用API
    from app.routes.api_routes import api_bp  # 一般的なAPI
    from app.routes.api.autoreply import autoreply_bp  # 自動返信API
    from app.routes.api.webhook import webhook_bp, configure_webhook  # WebhookAPI
    from app.routes.api.agents import agents_v3_bp  # 新しいエージェントAPI
    
    # 基本ブループリントを登録
    flask_app.register_blueprint(auth_bp, url_prefix='/auth')
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(profile_bp)
    flask_app.register_blueprint(public_bp)
    flask_app.register_blueprint(spot_bp)
    
    # API関連のブループリントを登録
    flask_app.register_blueprint(url_api_bp)  # URL検証用API
    flask_app.register_blueprint(api_bp)  # 一般的なAPI
    flask_app.register_blueprint(autoreply_bp)  # 自動返信API
    flask_app.register_blueprint(webhook_bp)  # WebhookAPI
    flask_app.register_blueprint(agents_v3_bp, url_prefix='/api/v3/agents')  # v3ブループリントを登録
    
    # webhook用のCSRF設定を適用
    configure_webhook(flask_app)
    
    # エージェントAPIのCSRF保護除外設定（webhook.pyと同じ方法）
    def configure_agents_csrf(app):
        """エージェントAPIのCSRF保護を設定"""
        try:
            print(f"Trying to configure agents: app={app}, type={type(app)}")
            print(f"App has extensions: {hasattr(app, 'extensions')}")
            if hasattr(app, 'extensions'):
                print(f"Available extensions: {app.extensions.keys()}")
            
            csrf_obj = getattr(app, 'csrf', None)
            if csrf_obj:
                print(f"CSRF object: {csrf_obj}, type={type(csrf_obj)}")
                csrf_obj.exempt(agents_v3_bp)
                app.logger.info("Agents v3 blueprint is now CSRF exempt")
            else:
                app.logger.warning("CSRF object not found on app")
        except Exception as e:
            app.logger.error(f"Error configuring agents CSRF: {str(e)}")
    
    configure_agents_csrf(flask_app)
    
    # エラーハンドラーの登録
    @flask_app.errorhandler(404)
    def page_not_found(e):
        """404エラーページ"""
        return render_template('public/404.html'), 404
    
    @flask_app.errorhandler(413)
    def request_entity_too_large(e):
        """413エラーページ（ファイルサイズ制限）"""
        from flask import flash, redirect, url_for, request
        
        # リクエストが来たエンドポイントを特定
        if request.endpoint and 'spot' in request.endpoint:
            flash('画像サイズが大きすぎます。1枚あたり10MB以下の画像をお選びください。', 'danger')
            return redirect(url_for('spot.add_spot'))
        else:
            flash('アップロードするファイルのサイズが大きすぎます。ファイルサイズを小さくしてお試しください。', 'danger')
            return redirect(url_for('profile.mypage'))
    
    @flask_app.errorhandler(500)
    def internal_server_error(e):
        """500エラーページ"""
        return render_template('public/500.html'), 500
    
    return flask_app 