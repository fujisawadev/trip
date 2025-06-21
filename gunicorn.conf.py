# Gunicorn設定ファイル
import os

# サーバー設定
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"
workers = int(os.environ.get('WEB_CONCURRENCY', 1))

# リクエスト制限設定
limit_request_line = 8190  # HTTPリクエストライン制限（デフォルト4094から増加）
limit_request_fields = 100  # HTTPヘッダーフィールド数制限
limit_request_field_size = 8190  # HTTPヘッダーフィールドサイズ制限

# ファイルアップロード対応
max_requests = 1000  # ワーカープロセスの最大リクエスト数
max_requests_jitter = 100  # リクエスト数のランダム変動幅
timeout = 120  # リクエストタイムアウト（ファイルアップロードを考慮して120秒）
keepalive = 2  # Keep-Alive接続のタイムアウト

# ログ設定
accesslog = '-'  # アクセスログを標準出力に
errorlog = '-'   # エラーログを標準出力に
loglevel = 'info'

# Heroku環境向け設定
preload_app = True  # アプリケーションの事前読み込み 