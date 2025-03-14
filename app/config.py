import os
import pathlib
import sys

# アプリケーションのルートディレクトリを取得
basedir = pathlib.Path(__file__).parent.parent.absolute()

class Config:
    """アプリケーションの基本設定"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string'
    
    # DATABASE_URLの処理（Herokuのpostgres:をpostgresql:に変換）
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("エラー: DATABASE_URL環境変数が設定されていません。")
        print("PostgreSQLデータベースへの接続情報を.envファイルに設定してください。")
        print("例: DATABASE_URL=postgresql://username:password@localhost:5432/trip_db")
        sys.exit(1)
    
    if database_url.startswith('postgres:'):
        database_url = database_url.replace('postgres:', 'postgresql:', 1)
    
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # PostgreSQL固有の設定
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_timeout': 30,
        'max_overflow': 2
    }
    
    # メール設定
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.sendgrid.net')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'apikey')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'support@its-capsule.com')
    
    # アップロード設定
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Instagram API設定
    INSTAGRAM_CLIENT_ID = os.environ.get('INSTAGRAM_CLIENT_ID')
    INSTAGRAM_CLIENT_SECRET = os.environ.get('INSTAGRAM_CLIENT_SECRET')
    
    @staticmethod
    def init_app(app):
        """アプリケーション初期化時の追加設定"""
        # アップロードディレクトリの作成
        try:
            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
            print(f"Created upload directory: {Config.UPLOAD_FOLDER}")
        except Exception as e:
            print(f"Error creating upload directory: {str(e)}") 