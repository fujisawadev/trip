import os
import traceback
import logging
from app import create_app, db

try:
    app = create_app()
    
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