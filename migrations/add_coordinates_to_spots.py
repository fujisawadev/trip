"""
スポットテーブルに緯度経度カラムを追加するマイグレーションスクリプト
"""
import sqlite3
import os

def run_migration():
    """マイグレーションを実行する"""
    # データベースファイルのパス
    db_path = os.path.join('app', 'app.db')
    
    # データベースに接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 既存のテーブルに緯度経度カラムを追加
        cursor.execute('ALTER TABLE spots ADD COLUMN latitude REAL;')
        cursor.execute('ALTER TABLE spots ADD COLUMN longitude REAL;')
        
        # 変更をコミット
        conn.commit()
        print("マイグレーション成功: スポットテーブルに緯度経度カラムを追加しました")
        
    except sqlite3.Error as e:
        # エラーが発生した場合はロールバック
        conn.rollback()
        print(f"マイグレーションエラー: {e}")
        
    finally:
        # 接続を閉じる
        conn.close()

if __name__ == "__main__":
    run_migration() 