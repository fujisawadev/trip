import os
import sys

# スクリプトのディレクトリをPYTHONPATHに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models.user import User
from app.models.spot import Spot
from app.models.photo import Photo
from app.models.social_account import SocialAccount
from app.models.social_post import SocialPost
from app.models.affiliate_link import AffiliateLink

def create_tables():
    """
    データベーステーブルを作成します。
    """
    app = create_app()
    with app.app_context():
        # テーブルを作成
        db.create_all()
        print("データベーステーブルを作成しました。")
        
        # テーブル一覧を表示
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print("作成されたテーブル:")
        for table in tables:
            print(f"- {table}")
            columns = inspector.get_columns(table)
            for column in columns:
                print(f"  - {column['name']}: {column['type']}")

if __name__ == "__main__":
    create_tables() 