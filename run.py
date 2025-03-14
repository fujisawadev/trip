import os
from app import create_app, db

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 8085))
    
    # 環境変数FLASK_ENVがdevelopmentの場合、またはローカルIPアドレスの場合にデバッグモードを有効にする
    # 環境変数が設定されていない場合はホスト名をチェックしてローカル環境かどうかを判断
    is_development = os.environ.get('FLASK_ENV') == 'development'
    is_local = os.environ.get('FLASK_DEBUG', '').lower() == 'true'
    
    # デフォルトでローカル開発時はデバッグモードを有効にする
    debug_mode = is_development or is_local or port == 8085
    
    app.run(host='0.0.0.0', debug=debug_mode, port=port) 