import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app, db
from app.models import User, Spot, Photo, SocialAccount

app = create_app()

def init_db():
    with app.app_context():
        # データベースの初期化
        db.drop_all()  # 既存のテーブルをすべて削除
        db.create_all()  # テーブルを新規作成
        
        print("データベースを初期化しました。")
        
        # テストユーザーの作成
        test_user = User(
            username="testuser",
            email="test@example.com",
            bio="This is a test user account."
        )
        test_user.set_password("password123")
        db.session.add(test_user)
        
        # ソーシャルアカウントの追加
        social = SocialAccount(
            user_id=1,  # テストユーザーのID
            instagram="testuser",
            twitter="testuser",
            tiktok="testuser",
            youtube="https://youtube.com/testuser"
        )
        db.session.add(social)
        
        # サンプルスポットの追加
        spot1 = Spot(
            user_id=1,
            name="Test Cafe",
            location="Tokyo, Japan",
            description="A cozy cafe with great coffee and atmosphere.",
            is_active=True
        )
        
        spot2 = Spot(
            user_id=1,
            name="Sakura Park",
            location="Kyoto, Japan",
            description="Beautiful park with cherry blossoms in spring.",
            is_active=True
        )
        
        db.session.add(spot1)
        db.session.add(spot2)
        db.session.commit()
        
        print("テストユーザーとサンプルデータを作成しました。")
        print("ログイン情報: email=test@example.com, password=password123")

if __name__ == "__main__":
    init_db() 