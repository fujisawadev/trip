import os
import redis
from rq import Worker, Queue

# Sentryの初期化を追加（メインアプリと同じ設定）
import sentry_sdk
from sentry_sdk.integrations.rq import RqIntegration

# Sentryの初期化 (HerokuアドオンなどでSENTRY_DSNが設定されている場合のみ)
if os.environ.get('SENTRY_DSN'):
    sentry_sdk.init(
        dsn=os.environ.get('SENTRY_DSN'),
        integrations=[
            RqIntegration(),  # RQ用のインテグレーション
        ],
        # パフォーマンストラッキングを有効にする
        traces_sample_rate=1.0,
        # 環境をセット
        environment=os.environ.get('FLASK_ENV', 'production'),
    )
    print(f"Sentry initialized for worker process (environment: {os.environ.get('FLASK_ENV', 'production')})")
else:
    print("SENTRY_DSN not found. Sentry monitoring disabled for worker process.")

# run.pyからFlask appをインポート
# このワーカープロセスがDB操作などFlaskの機能を使えるようにするため
from run import app

listen = ['default']

# Heroku RedisのURLまたはローカルのRedis URLを取得
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Redisへの接続を確立（SSL証明書検証を無効化）
conn = redis.from_url(redis_url, ssl_cert_reqs=None)

if __name__ == '__main__':
    # Flaskのアプリケーションコンテキスト内でワーカーを実行
    # これにより、ワーカー内のタスク（例: app/tasks.py）が
    # db.sessionなどのFlask拡張機能にアクセスできるようになる
    with app.app_context():
        # キューのリストを生成
        queues = [Queue(name, connection=conn) for name in listen]
        # ワーカーを生成し、指定されたキューを監視させる
        worker = Worker(queues, connection=conn)
        # ワーカーの処理を開始
        worker.work() 