import os
import sys
import json
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# データベースのURLを取得
DATABASE_URL = os.environ.get('DATABASE_URL')

# SQLiteデータベースのパス
SQLITE_DB_PATH = 'app/app.db'

def get_sqlite_tables():
    """SQLiteデータベースのテーブル一覧を取得"""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    conn.close()
    return [table[0] for table in tables if table[0] != 'sqlite_sequence']

def get_sqlite_data(table_name):
    """SQLiteデータベースからテーブルのデータを取得"""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name};")
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    conn.close()
    
    # 行データを辞書のリストに変換
    data = []
    for row in rows:
        row_dict = {}
        for i, column in enumerate(columns):
            row_dict[column] = row[i]
        data.append(row_dict)
    
    return columns, data

def get_postgres_connection():
    """PostgreSQLデータベースへの接続を取得"""
    # DATABASE_URLからパラメータを抽出
    if DATABASE_URL.startswith('postgresql://'):
        # 接続文字列からユーザー名、パスワード、ホスト、ポート、データベース名を抽出
        parts = DATABASE_URL.replace('postgresql://', '').split('@')
        user_pass = parts[0].split(':')
        host_port_db = parts[1].split('/')
        
        user = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else None
        
        host_port = host_port_db[0].split(':')
        host = host_port[0]
        port = host_port[1] if len(host_port) > 1 else '5432'
        
        dbname = host_port_db[1]
        
        # 接続
        if password:
            conn = psycopg2.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port
            )
        else:
            conn = psycopg2.connect(
                dbname=dbname,
                user=user,
                host=host,
                port=port
            )
        
        return conn
    else:
        raise ValueError("DATABASE_URL must start with postgresql://")

def convert_sqlite_value_to_postgres(table_name, column_name, value):
    """SQLiteの値をPostgreSQLの適切な型に変換"""
    # None値の処理
    if value is None:
        return None
    
    # ブール値の変換（SQLiteでは0/1、PostgreSQLではTrue/False）
    boolean_columns = {
        'spots': ['is_active'],
        'photos': ['is_google_photo'],
        'affiliate_links': ['is_active'],
        'social_posts': ['is_active'],
        'users': ['is_active']
    }
    
    if table_name in boolean_columns and column_name in boolean_columns[table_name]:
        if value == 1:
            return True
        elif value == 0:
            return False
    
    # 文字列の長さ制限
    varchar_255_columns = {
        'spots': ['name', 'address', 'photo_url', 'google_place_id', 'google_photo_reference'],
        'photos': ['url', 'google_photo_reference'],
        'users': ['username', 'email', 'profile_pic_url'],
        'social_accounts': ['platform', 'username', 'profile_url'],
        'affiliate_links': ['platform', 'url', 'tracking_id'],
        'social_posts': ['platform', 'post_url']
    }
    
    if table_name in varchar_255_columns and column_name in varchar_255_columns[table_name] and isinstance(value, str):
        return value[:255] if len(value) > 255 else value
    
    return value

def alter_table_column_type(conn, table_name, column_name, new_type):
    """テーブルのカラム型を変更"""
    cursor = conn.cursor()
    cursor.execute(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {new_type};")
    conn.commit()

def migrate_data():
    """SQLiteからPostgreSQLにデータを移行"""
    tables = get_sqlite_tables()
    print(f"Found tables: {tables}")
    
    # テーブルの順序を依存関係に基づいて並べ替え
    # 外部キー制約を満たすために、親テーブルを先に移行する
    table_order = [
        'users',
        'spots',
        'photos',
        'social_accounts',
        'affiliate_links',
        'social_posts',
        'alembic_version'
    ]
    
    # 存在するテーブルのみをフィルタリング
    ordered_tables = [table for table in table_order if table in tables]
    # リストにないテーブルを追加
    for table in tables:
        if table not in ordered_tables:
            ordered_tables.append(table)
    
    # PostgreSQL接続
    pg_conn = get_postgres_connection()
    pg_cursor = pg_conn.cursor()
    
    # 外部キー制約を一時的に無効化
    pg_cursor.execute("SET session_replication_role = 'replica';")
    pg_conn.commit()
    
    # テキスト型のカラムを拡張
    try:
        # spotsテーブルのカラムを拡張
        alter_table_column_type(pg_conn, 'spots', 'name', 'TEXT')
        alter_table_column_type(pg_conn, 'spots', 'address', 'TEXT')
        alter_table_column_type(pg_conn, 'spots', 'photo_url', 'TEXT')
        alter_table_column_type(pg_conn, 'spots', 'google_place_id', 'TEXT')
        alter_table_column_type(pg_conn, 'spots', 'google_photo_reference', 'TEXT')
        
        # photosテーブルのカラムを拡張
        alter_table_column_type(pg_conn, 'photos', 'url', 'TEXT')
        alter_table_column_type(pg_conn, 'photos', 'google_photo_reference', 'TEXT')
        
        # usersテーブルのカラムを拡張
        alter_table_column_type(pg_conn, 'users', 'profile_pic_url', 'TEXT')
        
        # social_accountsテーブルのカラムを拡張
        alter_table_column_type(pg_conn, 'social_accounts', 'profile_url', 'TEXT')
        
        # affiliate_linksテーブルのカラムを拡張
        alter_table_column_type(pg_conn, 'affiliate_links', 'url', 'TEXT')
        
        # social_postsテーブルのカラムを拡張
        alter_table_column_type(pg_conn, 'social_posts', 'post_url', 'TEXT')
        
        print("Successfully altered column types to TEXT")
    except Exception as e:
        print(f"Warning: Could not alter column types: {e}")
    
    for table in ordered_tables:
        try:
            print(f"Migrating table: {table}")
            columns, data = get_sqlite_data(table)
            
            if not data:
                print(f"No data in table {table}, skipping...")
                continue
            
            # カラム名のリスト
            column_names = ", ".join(columns)
            
            # 値のプレースホルダー
            placeholders = ", ".join(["%s"] * len(columns))
            
            # データの変換と挿入
            values = []
            for row in data:
                row_values = []
                for col in columns:
                    # SQLiteの値をPostgreSQLの適切な型に変換
                    converted_value = convert_sqlite_value_to_postgres(table, col, row[col])
                    row_values.append(converted_value)
                values.append(row_values)
            
            # シーケンスをリセット（自動採番カラムがある場合）
            if 'id' in columns:
                try:
                    max_id = max(row['id'] for row in data)
                    pg_cursor.execute(f"SELECT setval('{table}_id_seq', {max_id}, true);")
                except Exception as e:
                    print(f"Warning: Could not reset sequence for {table}: {e}")
            
            # データの挿入
            execute_values(
                pg_cursor,
                f"INSERT INTO {table} ({column_names}) VALUES %s ON CONFLICT DO NOTHING;",
                values,
                template=f"({placeholders})"
            )
            
            pg_conn.commit()
            print(f"Successfully migrated {len(data)} rows to {table}")
            
        except Exception as e:
            pg_conn.rollback()
            print(f"Error migrating table {table}: {e}")
    
    # 外部キー制約を再度有効化
    pg_cursor.execute("SET session_replication_role = 'origin';")
    pg_conn.commit()
    
    pg_conn.close()
    print("Migration completed!")

if __name__ == "__main__":
    print("Starting migration from SQLite to PostgreSQL...")
    migrate_data()
    print("Migration process finished!") 