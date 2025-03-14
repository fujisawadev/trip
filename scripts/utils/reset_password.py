#!/usr/bin/env python
import os
import sys

# ルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import create_app, db, bcrypt
from app.models.user import User

def reset_password():
    """ユーザーID 1のパスワードを「1234」にリセットする"""
    app = create_app()
    with app.app_context():
        user = User.query.get(1)
        if user:
            # パスワードをリセット
            user.set_password('1234')
            db.session.commit()
            print(f'ユーザー {user.username} (ID: {user.id}) のパスワードが「1234」にリセットされました。')
            print(f'メールアドレス: {user.email}')
            print(f'パスワードハッシュ: {user.password_hash}')
        else:
            print('ユーザーID 1が見つかりません。')

if __name__ == '__main__':
    reset_password() 