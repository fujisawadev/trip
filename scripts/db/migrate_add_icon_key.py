import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app, db
from app.models import AffiliateLink
from alembic import op
import sqlalchemy as sa

app = create_app()

def migrate():
    with app.app_context():
        # affiliate_linksテーブルにicon_keyカラムを追加
        try:
            op.add_column('affiliate_links', sa.Column('icon_key', sa.String(50), nullable=True))
            print("affiliate_linksテーブルにicon_keyカラムを追加しました。")
        except Exception as e:
            print(f"affiliate_linksテーブルの更新中にエラーが発生しました: {str(e)}")
            # SQLAlchemyを使用して直接カラムを追加
            try:
                engine = db.engine
                engine.execute('ALTER TABLE affiliate_links ADD COLUMN icon_key VARCHAR(50)')
                print("SQLAlchemyを使用してicon_keyカラムを追加しました。")
            except Exception as e2:
                print(f"SQLAlchemyを使用したカラム追加中にエラーが発生しました: {str(e2)}")
                print("カラムが既に存在する場合は無視してください。")
        
        # 既存のアフィリエイトリンクにicon_keyを設定
        try:
            # プラットフォームに基づいてicon_keyを設定
            platform_to_icon = {
                'booking': 'booking-com',
                'rakuten': 'rakuten-travel',
                'jalan': 'jalan',
                'expedia': 'expedia',
                'agoda': 'agoda'
            }
            
            # すべてのアフィリエイトリンクを取得
            links = AffiliateLink.query.all()
            updated_count = 0
            
            for link in links:
                if link.platform in platform_to_icon:
                    link.icon_key = platform_to_icon[link.platform]
                    updated_count += 1
            
            db.session.commit()
            print(f"{updated_count}件のアフィリエイトリンクにicon_keyを設定しました。")
            
        except Exception as e:
            print(f"既存データの更新中にエラーが発生しました: {str(e)}")
            db.session.rollback()

if __name__ == "__main__":
    migrate() 