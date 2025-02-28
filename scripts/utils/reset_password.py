import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app, db, bcrypt
from app.models.user import User

def reset_password():
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email='test@example.com').first()
        if user:
            user.password_hash = bcrypt.generate_password_hash('password').decode('utf-8')
            db.session.commit()
            print('パスワードをリセットしました。')
        else:
            print('ユーザーが見つかりません。')

if __name__ == '__main__':
    reset_password() 