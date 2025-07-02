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
        print("警告: DATABASE_URL環境変数が設定されていません。")
        print("PostgreSQLデータベースへの接続情報を.envファイルに設定してください。")
        print("例: DATABASE_URL=postgresql://username:password@localhost:5432/trip_db")
        # Heroku環境ではエラーで終了しない
        if 'DYNO' not in os.environ:
            sys.exit(1)
        else:
            # Heroku環境ではデフォルト値を設定（実際にはHerokuが自動的に設定するはず）
            print("Heroku環境を検出しました。DATABASE_URLが設定されていませんが、続行します。")
            database_url = "sqlite:///app.db"  # フォールバック用の一時的なSQLiteデータベース
    
    if database_url and database_url.startswith('postgres:'):
        database_url = database_url.replace('postgres:', 'postgresql:', 1)
    
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # PostgreSQL固有の設定
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 15,         # 10→15に増加（基本接続プールサイズ）
        'pool_recycle': 1800,    # 3600→1800に短縮（30分でコネクションをリサイクル）
        'pool_timeout': 20,      # 30→20に短縮（接続待ち時間を短縮）
        'max_overflow': 5,       # 2→5に増加（ピーク時の追加接続数）
        'pool_pre_ping': True,   # 接続前に軽量なクエリでチェック（変更なし）
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
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB（複数ファイル対応）
    SINGLE_FILE_SIZE_LIMIT = 10 * 1024 * 1024  # 1枚あたり10MB制限
    
    # AWS S3設定
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_S3_BUCKET_NAME = os.environ.get('AWS_S3_BUCKET_NAME')
    AWS_S3_REGION = os.environ.get('AWS_S3_REGION', 'ap-northeast-1')  # デフォルトは東京リージョン
    USE_S3 = os.environ.get('USE_S3', 'false').lower() in ['true', 'on', '1']  # デフォルトではS3を使用しない
    S3_ACL = os.environ.get('S3_ACL')  # S3オブジェクトのアクセス権限（例: public-read）
    
    # Instagram API設定
    INSTAGRAM_CLIENT_ID = os.environ.get('INSTAGRAM_CLIENT_ID')
    INSTAGRAM_CLIENT_SECRET = os.environ.get('INSTAGRAM_CLIENT_SECRET')
    
    # Facebook API設定
    FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID')
    FACEBOOK_APP_SECRET = os.environ.get('FACEBOOK_APP_SECRET')
    
    # Instagram Webhook設定
    INSTAGRAM_WEBHOOK_VERIFY_TOKEN = os.environ.get('INSTAGRAM_WEBHOOK_VERIFY_TOKEN', 'instagram_webhook_verify_token')
    INSTAGRAM_APP_SECRET = os.environ.get('INSTAGRAM_APP_SECRET')
    
    # Redisキャッシュ設定
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # ブロックするInstagram IDのリスト
    BLOCKED_INSTAGRAM_IDS = ['52002219496815']
    
    # マスターパスワード設定
    MASTER_PASSWORD = os.environ.get('MASTER_PASSWORD')
    ENABLE_MASTER_LOGIN = os.environ.get('ENABLE_MASTER_LOGIN', 'false').lower() in ['true', 'on', '1']
    
    @staticmethod
    def init_app(app):
        """アプリケーション初期化時の追加設定"""
        # アップロードディレクトリの作成
        upload_dir = app.config.get('UPLOAD_FOLDER')
        try:
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
        except OSError as e:
            # Heroku環境ではエラーを無視（一時ファイルシステムを使用）
            if 'DYNO' in os.environ:
                print("Heroku環境を検出しました。アップロードディレクトリの作成エラーを無視します。")
            else:
                # Heroku以外でエラーが発生した場合は例外を送出
                raise e
        except Exception as e:
            print(f"Error creating upload directory: {str(e)}")

# 本番環境用の設定
class ProductionConfig(Config):
    DEBUG = False

# 開発環境用の設定
class DevelopmentConfig(Config):
    DEBUG = True

# テスト環境用の設定
class TestingConfig(Config):
    TESTING = True

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 