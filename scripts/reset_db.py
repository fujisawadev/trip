import os
import sys
import traceback
import psycopg2
from dotenv import load_dotenv

# スクリプトのディレクトリをPYTHONPATHに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 環境変数の読み込み
load_dotenv()

def reset_database():
    """
    PostgreSQLデータベースをリセットします。
    既存の接続をすべて終了し、テーブルをリセットします。
    """
    # データベース接続情報を取得
    db_url = os.environ.get('DATABASE_URL')
    print(f"データベースURL: {db_url}")
    
    if not db_url or not db_url.startswith('postgresql'):
        print("PostgreSQLデータベースのURLが設定されていません。")
        return False
    
    # 接続情報をパース
    # postgresql://username:password@host:port/dbname
    db_url = db_url.replace('postgresql://', '')
    if '@' in db_url:
        auth, rest = db_url.split('@')
        if ':' in auth:
            username, password = auth.split(':')
        else:
            username, password = auth, ''
        
        if '/' in rest:
            host_port, dbname = rest.split('/')
            if ':' in host_port:
                host, port = host_port.split(':')
            else:
                host, port = host_port, '5432'
        else:
            host, port, dbname = rest, '5432', ''
    else:
        print("データベースURLの形式が正しくありません。")
        return False
    
    print(f"接続情報: host={host}, port={port}, user={username}, dbname={dbname}")
    
    try:
        # データベースに接続
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            dbname=dbname
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # 既存の接続をすべて終了
        cursor.execute("""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = %s
        AND pid <> pg_backend_pid();
        """, (dbname,))
        
        print("既存の接続をすべて終了しました。")
        
        # テーブルをリセット
        cursor.execute("DROP SCHEMA public CASCADE;")
        cursor.execute("CREATE SCHEMA public;")
        cursor.execute("GRANT ALL ON SCHEMA public TO public;")
        
        print("データベースをリセットしました。")
        
        cursor.close()
        conn.close()
        return True
    
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("データベースリセットスクリプトを実行します...")
    if reset_database():
        print("データベースのリセットが完了しました。")
        print("次に以下のコマンドを実行してマイグレーションを適用してください：")
        print("flask db upgrade")
    else:
        print("データベースのリセットに失敗しました。") 