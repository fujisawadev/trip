import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app, db
from app.models import Spot, AffiliateLink, SocialPost
from alembic import op
import sqlalchemy as sa

app = create_app()

def migrate():
    with app.app_context():
        # Spotテーブルにgoogle_maps_urlカラムを追加
        try:
            op.add_column('spots', sa.Column('google_maps_url', sa.String(255), nullable=True))
            print("Spotテーブルにgoogle_maps_urlカラムを追加しました。")
        except Exception as e:
            print(f"Spotテーブルの更新中にエラーが発生しました: {str(e)}")
            # SQLAlchemyを使用して直接カラムを追加
            try:
                engine = db.engine
                engine.execute('ALTER TABLE spots ADD COLUMN google_maps_url VARCHAR(255)')
                print("SQLAlchemyを使用してgoogle_maps_urlカラムを追加しました。")
            except Exception as e2:
                print(f"SQLAlchemyを使用したカラム追加中にエラーが発生しました: {str(e2)}")
                print("カラムが既に存在する場合は無視してください。")
        
        # affiliate_linksテーブルを作成
        try:
            AffiliateLink.__table__.create(db.engine)
            print("affiliate_linksテーブルを作成しました。")
        except Exception as e:
            print(f"affiliate_linksテーブル作成中にエラーが発生しました: {str(e)}")
            print("テーブルが既に存在する場合は無視してください。")
        
        # social_postsテーブルを作成
        try:
            SocialPost.__table__.create(db.engine)
            print("social_postsテーブルを作成しました。")
        except Exception as e:
            print(f"social_postsテーブル作成中にエラーが発生しました: {str(e)}")
            print("テーブルが既に存在する場合は無視してください。")
        
        print("マイグレーションが完了しました。")

if __name__ == "__main__":
    migrate() 