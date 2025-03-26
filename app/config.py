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
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_timeout': 30,
        'max_overflow': 2,
        'pool_pre_ping': True,  # 接続前に軽量なクエリでチェック
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
    
    @staticmethod
    def init_app(app):
        """アプリケーション初期化時の追加設定"""
        # アップロードディレクトリの作成
        try:
            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
            print(f"Created upload directory: {Config.UPLOAD_FOLDER}")
        except Exception as e:
            print(f"Error creating upload directory: {str(e)}")
            # Heroku環境ではエラーを無視（一時ファイルシステムを使用）
            if 'DYNO' in os.environ:
                print("Heroku環境を検出しました。アップロードディレクトリの作成エラーを無視します。") 