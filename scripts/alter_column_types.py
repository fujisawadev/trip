import os
import sys

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from sqlalchemy import text

def alter_column_types():
    """カラムの型をVARCHARからTEXTに変更する"""
    app = create_app()
    with app.app_context():
        # spotsテーブルのカラムを変更
        with db.engine.begin() as conn:
            conn.execute(text('''
                ALTER TABLE spots 
                ALTER COLUMN name TYPE TEXT,
                ALTER COLUMN location TYPE TEXT,
                ALTER COLUMN google_place_id TYPE TEXT,
                ALTER COLUMN formatted_address TYPE TEXT,
                ALTER COLUMN thumbnail_url TYPE TEXT,
                ALTER COLUMN google_photo_reference TYPE TEXT,
                ALTER COLUMN summary_location TYPE TEXT,
                ALTER COLUMN google_maps_url TYPE TEXT
            '''))
            
            # photosテーブルのカラムを変更
            conn.execute(text('''
                ALTER TABLE photos
                ALTER COLUMN photo_url TYPE TEXT,
                ALTER COLUMN google_photo_reference TYPE TEXT
            '''))
            
            # usersテーブルのカラムを変更
            conn.execute(text('''
                ALTER TABLE users
                ALTER COLUMN password_hash TYPE TEXT,
                ALTER COLUMN profile_pic_url TYPE TEXT
            '''))
            
            # social_accountsテーブルのカラムを変更
            conn.execute(text('''
                ALTER TABLE social_accounts
                ALTER COLUMN instagram TYPE TEXT,
                ALTER COLUMN twitter TYPE TEXT,
                ALTER COLUMN tiktok TYPE TEXT,
                ALTER COLUMN youtube TYPE TEXT,
                ALTER COLUMN account_id TYPE TEXT
            '''))
            
            # affiliate_linksテーブルのカラムを変更
            conn.execute(text('''
                ALTER TABLE affiliate_links
                ALTER COLUMN url TYPE TEXT,
                ALTER COLUMN title TYPE TEXT,
                ALTER COLUMN description TYPE TEXT,
                ALTER COLUMN logo_url TYPE TEXT
            '''))
            
            # social_postsテーブルのカラムを変更
            conn.execute(text('''
                ALTER TABLE social_posts
                ALTER COLUMN post_url TYPE TEXT,
                ALTER COLUMN post_id TYPE TEXT,
                ALTER COLUMN thumbnail_url TYPE TEXT
            '''))
        
        print("カラムの型をVARCHARからTEXTに変更しました。")

if __name__ == "__main__":
    alter_column_types() 