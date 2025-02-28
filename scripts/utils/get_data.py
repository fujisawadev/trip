import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app, db
from app.models import User, Spot, Photo

def get_data():
    app = create_app()
    with app.app_context():
        users = User.query.all()
        print('=== ユーザー一覧 ===')
        for user in users:
            print(f'ID: {user.id}, ユーザー名: {user.username}, メール: {user.email}')
        
        print('\n=== スポット一覧 ===')
        spots = Spot.query.all()
        for spot in spots:
            print(f'ID: {spot.id}, 名前: {spot.name}, ユーザーID: {spot.user_id}, 公開: {spot.is_active}')

if __name__ == "__main__":
    get_data() 