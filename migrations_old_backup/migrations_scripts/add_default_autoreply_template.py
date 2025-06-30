#!/usr/bin/env python3
"""
既存のユーザーにデフォルトの自動返信テンプレートを設定するスクリプト
"""
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import db, create_app
from app.models.user import User

def add_default_template():
    """すべてのユーザーに対してデフォルトのテンプレートを設定する"""
    app = create_app()
    with app.app_context():
        # テンプレートが未設定（Noneまたは空文字）のユーザーを検索
        users = User.query.filter(
            (User.autoreply_template == None) | 
            (User.autoreply_template == '')
        ).all()
        
        count = 0
        for user in users:
            user.autoreply_template = 'ご質問ありがとうございます！スポットの詳細はこちらのプロフィールページでご確認いただけます：{profile_url}'
            count += 1
        
        # 変更を保存
        db.session.commit()
        print(f"{count}人のユーザーにデフォルトテンプレートを設定しました")

if __name__ == "__main__":
    add_default_template() 