import os
import traceback
import logging
from app import create_app, db
from flask.cli import with_appcontext
import click

try:
    app = create_app()

    # CLI: wallet aggregations (Flask CLI登録はimport時に実行される必要がある)
    @click.command('wallet-daily')
    @click.option('--day', default=None, help='YYYY-MM-DD（省略時は前日）')
    @with_appcontext
    def wallet_daily(day):
        from app.tasks import run_daily_wallet_aggregation
        from datetime import datetime as _dt
        target = _dt.strptime(day, '%Y-%m-%d').date() if day else None
        run_daily_wallet_aggregation(target)
        click.echo('daily aggregation done')

    @click.command('wallet-monthly')
    @click.option('--month', default=None, help='YYYY-MM-01（省略時は前月）')
    @with_appcontext
    def wallet_monthly(month):
        from app.tasks import run_monthly_wallet_close
        from datetime import datetime as _dt
        target = _dt.strptime(month, '%Y-%m-%d').date() if month else None
        run_monthly_wallet_close(target)
        click.echo('monthly close done')

    app.cli.add_command(wallet_daily)
    app.cli.add_command(wallet_monthly)

    # Stripe Transfer バッチ（72時間クールダウン経過分の引き出しを処理）
    @click.command('wallet-transfers')
    @with_appcontext
    def wallet_transfers():
        from app.tasks import run_withdrawal_cooldown_and_transfer
        run_withdrawal_cooldown_and_transfer()
        click.echo('wallet transfers batch done')

    app.cli.add_command(wallet_transfers)

    # Instagram 長期トークンの定期リフレッシュ（Scheduler想定）
    @click.command('ig-refresh')
    @click.option('--dry-run', is_flag=True, default=False, help='実更新せず対象とログだけ出す')
    @click.option('--days', default=14, help='有効期限までの閾値（日）')
    @with_appcontext
    def ig_refresh(dry_run: bool, days: int):
        from datetime import datetime, timedelta
        from app import db
        from app.models.user import User
        from app.utils.instagram_helpers import (
            refresh_user_instagram_token_if_needed,
            validate_instagram_token,
        )

        now = datetime.utcnow()
        horizon = now + timedelta(days=days)

        users = (User.query
                 .filter(User.instagram_token.isnot(None))
                 .filter((User.instagram_token_expires_at == None) | (User.instagram_token_expires_at <= horizon))
                 .all())

        success_count = 0
        failed_count = 0

        for user in users:
            if dry_run:
                exp = user.instagram_token_expires_at.isoformat() if user.instagram_token_expires_at else 'None'
                app.logger.info(f"[IG DRY-RUN] user={user.id} ({user.username}) expires_at={exp}")
                continue

            ok, reason = validate_instagram_token(user)
            if not ok and reason in ['invalid', 'expired', 'no_token']:
                # 無効/期限切れはUIで再連携を促せるようにクリア
                app.logger.info(f"[IG] invalid token -> clear fields user={user.id} reason={reason}")
                user.instagram_token = None
                user.instagram_token_expires_at = None
                user.instagram_token_last_refreshed_at = None
                user.instagram_connected_at = None
                user.instagram_business_id = None
                failed_count += 1
                continue

            if refresh_user_instagram_token_if_needed(user, threshold_days=days):
                success_count += 1

        if not dry_run:
            db.session.commit()

        click.echo(f"ig refresh done: success={success_count}, failed={failed_count}, targeted={len(users)}")

    app.cli.add_command(ig_refresh)

    # ログ設定を強化
    logging.basicConfig(level=logging.DEBUG)
    
    # Heroku環境かどうかを判定する関数
    def is_heroku():
        return 'DYNO' in os.environ
    
    if __name__ == '__main__':
        try:
            with app.app_context():
                db.create_all()
            
            # Heroku環境ではPROCFILEでポートが指定されるため、ここでの設定は無視される
            port = int(os.environ.get('PORT', 8085))
            
            # 環境変数FLASK_ENVがdevelopmentの場合、またはローカルIPアドレスの場合にデバッグモードを有効にする
            # 環境変数が設定されていない場合はホスト名をチェックしてローカル環境かどうかを判断
            is_development = os.environ.get('FLASK_ENV') == 'development'
            is_local = os.environ.get('FLASK_DEBUG', '').lower() == 'true'
            
            # デフォルトでローカル開発時はデバッグモードを有効にする
            # Heroku環境ではデバッグモードを無効にする
            debug_mode = (is_development or is_local or port == 8085) and not is_heroku()
            
            # ローカル開発環境でHTTPSを使用するための設定
            # 自己署名証明書を使用（開発環境のみ）
            ssl_context = None
            
            # Heroku環境ではSSLを無効化（Herokuは独自のSSL終端を提供）
            # ローカル開発環境でも、証明書が存在し、明示的にHTTPS有効化が指定された場合のみHTTPS使用
            if not is_heroku() and os.environ.get('USE_HTTPS', '').lower() == 'true':
                # 証明書ファイルのパスを指定
                cert_path = os.environ.get('SSL_CERT_PATH', 'localhost.crt')
                key_path = os.environ.get('SSL_KEY_PATH', 'localhost.key')
                
                # 証明書ファイルが存在する場合のみSSLを有効化
                if os.path.exists(cert_path) and os.path.exists(key_path):
                    ssl_context = (cert_path, key_path)
                    print(f"HTTPS有効化: 証明書 {cert_path}, キー {key_path}")
                else:
                    print(f"警告: 証明書ファイルが見つかりません。HTTPSは無効化されます。")
                    print(f"証明書パス: {cert_path}, キーパス: {key_path}")
                    print(f"ローカル開発環境ではHTTPを使用してください: http://localhost:{port}")
            else:
                # デフォルトではHTTPを使用（ローカル開発環境）
                print(f"ローカル開発環境: HTTPで起動します: http://localhost:{port}")
            
            # Heroku環境ではPROCFILEを使用するため、この行は実行されない
            if not is_heroku():
                app.run(host='0.0.0.0', debug=debug_mode, port=port, ssl_context=ssl_context)
            else:
                # Heroku環境では、PROCFILEとの互換性のために何もしない
                pass
        except Exception as e:
            print("アプリケーション実行中にエラーが発生しました:")
            traceback.print_exc()
except Exception as e:
    print("アプリケーション初期化中にエラーが発生しました:")
    traceback.print_exc() 