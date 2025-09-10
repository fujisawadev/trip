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
    
    # エンジンオプション（SQLiteではプール関連を外す）
    if database_url and database_url.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 15,
            'pool_recycle': 1800,
            'pool_timeout': 20,
            'max_overflow': 5,
            'pool_pre_ping': True,
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

    # Travelpayouts 設定（廃止）: 参照していないため削除済み

    # Agoda アフィリエイト設定（deeplink用）
    AGODA_PARTNER_ID = os.environ.get('AGODA_PARTNER_ID')  # 通常 'cid'
    AGODA_CAMPAIGN_ID = os.environ.get('AGODA_CAMPAIGN_ID')  # 任意: サブキャンペーン
    AGODA_LOCALE = os.environ.get('AGODA_LOCALE', 'ja-jp')
    AGODA_CURRENCY = os.environ.get('AGODA_CURRENCY', 'JPY')
    # Agoda Search API 用プレースホルダ（承認・仕様に応じて利用）
    AGODA_API_BASE = os.environ.get('AGODA_API_BASE', 'https://partners.agoda.com')
    AGODA_API_KEY = os.environ.get('AGODA_API_KEY')
    AGODA_API_TOKEN = os.environ.get('AGODA_API_TOKEN')
    AGODA_SITE_ID = os.environ.get('AGODA_SITE_ID')
    AGODA_AFFILIATE_LITE_URL = os.environ.get('AGODA_AFFILIATE_LITE_URL')
    
    # DataForSEO（Google Hotelsのメタサーチ相当）
    DATAFORSEO_BASE_URL = os.environ.get('DATAFORSEO_BASE_URL', 'https://api.dataforseo.com')
    DATAFORSEO_LOGIN = os.environ.get('DATAFORSEO_LOGIN')
    DATAFORSEO_PASSWORD = os.environ.get('DATAFORSEO_PASSWORD')
    DATAFORSEO_DEFAULT_LOCATION = os.environ.get('DATAFORSEO_DEFAULT_LOCATION', 'Japan')
    DATAFORSEO_DEFAULT_LANGUAGE = os.environ.get('DATAFORSEO_DEFAULT_LANGUAGE', 'ja')

    # 楽天トラベル
    RAKUTEN_AFFILIATE_ID = os.environ.get('RAKUTEN_AFFILIATE_ID')
    
    # Wallet/Analytics 設定
    WALLET_TZ = os.environ.get('WALLET_TZ', 'Asia/Tokyo')
    WALLET_PPV_FLOOR = float(os.environ.get('WALLET_PPV_FLOOR', '0.01'))
    WALLET_CPC_BASE = float(os.environ.get('WALLET_CPC_BASE', '3.0'))
    WALLET_PPV_CAP = float(os.environ.get('WALLET_PPV_CAP', '0.10'))
    WALLET_PPV_CAP_NEWBIE = float(os.environ.get('WALLET_PPV_CAP_NEWBIE', '0.07'))
    WALLET_CPC_MIN = float(os.environ.get('WALLET_CPC_MIN', '2.0'))
    WALLET_CPC_MAX = float(os.environ.get('WALLET_CPC_MAX', '5.0'))
    WALLET_GLOBAL_DAILY_BUDGET = float(os.environ.get('WALLET_GLOBAL_DAILY_BUDGET', '500000'))
    WALLET_CREATOR_DAILY_CAP = float(os.environ.get('WALLET_CREATOR_DAILY_CAP', '20000'))
    WALLET_BURST_FACTOR = float(os.environ.get('WALLET_BURST_FACTOR', '3.0'))
    WALLET_BURST_CAP_REDUCTION = float(os.environ.get('WALLET_BURST_CAP_REDUCTION', '0.20'))  # 20%

    # Stripe/Wallet Payout 設定
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    MIN_PAYOUT_YEN = int(os.environ.get('MIN_PAYOUT_YEN', '1000'))
    LARGE_PAYOUT_YEN = int(os.environ.get('LARGE_PAYOUT_YEN', '100000'))
    TARGET_FLOAT_FACTOR = float(os.environ.get('TARGET_FLOAT_FACTOR', '1.3'))
    APP_BASE_URL = os.environ.get('APP_BASE_URL', os.environ.get('BASE_URL', 'http://localhost:5000'))
    
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