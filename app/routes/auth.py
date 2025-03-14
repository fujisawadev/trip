from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db, mail
from app.models.user import User
from werkzeug.urls import url_parse
from flask_mail import Message
import os
import requests
import json

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """サインアップページ"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    if request.method == 'POST':
        username = request.form.get('fullName')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 入力チェック
        if not username or not email or not password:
            flash('すべての項目を入力してください。', 'danger')
            return render_template('signup.html')
        
        # ユーザー名とメールアドレスの重複チェック
        if User.query.filter_by(username=username).first():
            flash('このユーザー名は既に使用されています。', 'danger')
            return render_template('signup.html')
        
        if User.query.filter_by(email=email).first():
            flash('このメールアドレスは既に登録されています。', 'danger')
            return render_template('signup.html')
        
        # ユーザー作成
        user = User(username=username, email=email, password=password)
        db.session.add(user)
        db.session.commit()
        
        flash('アカウントが作成されました。ログインしてください。', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('signup.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """ログインページ"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        print(f"ログイン試行: メール={email}, パスワード={password}")  # デバッグ用
        
        # 入力チェック
        if not email or not password:
            flash('メールアドレスとパスワードを入力してください。', 'danger')
            return render_template('login.html')
        
        # ユーザー認証
        user = User.query.filter_by(email=email).first()
        print(f"ユーザー検索結果: {user is not None}")  # デバッグ用
        
        if user is None or not user.check_password(password):
            print(f"パスワード検証: {user.check_password(password) if user else 'ユーザーが見つかりません'}")  # デバッグ用
            flash('メールアドレスまたはパスワードが正しくありません。', 'danger')
            return render_template('login.html')
        
        # ログイン
        login_user(user, remember=remember)
        print(f"ログイン成功: ユーザーID={user.id}")  # デバッグ用
        
        # リダイレクト先の処理
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('profile.mypage')
        
        flash('ログインしました。', 'success')
        return redirect(next_page)
    
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    """ログアウト処理"""
    logout_user()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/change-email', methods=['GET', 'POST'])
@login_required
def change_email():
    """メールアドレス変更ページ"""
    if request.method == 'POST':
        new_email = request.form.get('new_email')
        confirm_email = request.form.get('confirm_email')
        password = request.form.get('password')
        
        # 入力チェック
        if not new_email or not confirm_email or not password:
            flash('すべての項目を入力してください。', 'danger')
            return render_template('change_email.html', user=current_user)
        
        # メールアドレスの一致チェック
        if new_email != confirm_email:
            flash('新しいメールアドレスが一致しません。', 'danger')
            return render_template('change_email.html', user=current_user)
        
        # パスワード認証
        if not current_user.check_password(password):
            flash('パスワードが正しくありません。', 'danger')
            return render_template('change_email.html', user=current_user)
        
        # メールアドレスの重複チェック
        if User.query.filter_by(email=new_email).first():
            flash('このメールアドレスは既に使用されています。', 'danger')
            return render_template('change_email.html', user=current_user)
        
        # メールアドレスの更新
        current_user.email = new_email
        db.session.commit()
        
        flash('メールアドレスが更新されました。', 'success')
        return redirect(url_for('profile.account_settings'))
    
    return render_template('change_email.html', user=current_user)

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """パスワード変更ページ"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 入力チェック
        if not current_password or not new_password or not confirm_password:
            flash('すべての項目を入力してください。', 'danger')
            return render_template('change_password.html')
        
        # 現在のパスワード認証
        if not current_user.check_password(current_password):
            flash('現在のパスワードが正しくありません。', 'danger')
            return render_template('change_password.html')
        
        # 新しいパスワードの一致チェック
        if new_password != confirm_password:
            flash('新しいパスワードが一致しません。', 'danger')
            return render_template('change_password.html')
        
        # パスワードの強度チェック
        if len(new_password) < 8:
            flash('パスワードは8文字以上である必要があります。', 'danger')
            return render_template('change_password.html')
        
        # パスワードの更新
        current_user.set_password(new_password)
        db.session.commit()
        
        flash('パスワードが更新されました。', 'success')
        return redirect(url_for('profile.account_settings'))
    
    return render_template('change_password.html')

@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """パスワードリセットリクエストページ"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        
        # 入力チェック
        if not email:
            flash('メールアドレスを入力してください。', 'danger')
            return render_template('forgot_password.html')
        
        # ユーザー検索
        user = User.query.filter_by(email=email).first()
        if user:
            # リセットトークンを生成
            token = user.generate_reset_token()
            
            try:
                # リセットURLの生成
                reset_url = url_for('auth.reset_password', token=token, _external=True)
                print(f"リセットURL: {reset_url}")
                print(f"送信先メールアドレス: {user.email}")
                
                # SendGridのWeb APIを使用してメール送信
                url = "https://api.sendgrid.com/v3/mail/send"
                headers = {
                    "Authorization": f"Bearer {os.environ.get('MAIL_PASSWORD')}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "personalizations": [
                        {
                            "to": [
                                {
                                    "email": user.email
                                }
                            ],
                            "subject": "Password Reset Request"
                        }
                    ],
                    "from": {
                        "email": "support@its-capsule.com"
                    },
                    "content": [
                        {
                            "type": "text/plain",
                            "value": f"Click the link below to reset your password:\n{reset_url}\n\nThis link will expire in 24 hours.\n\nIf you did not request a password reset, please ignore this email."
                        }
                    ]
                }
                
                response = requests.post(url, headers=headers, data=json.dumps(data))
                print(f"SendGrid レスポンス: {response.status_code}")
                
                if response.status_code != 202:
                    print(f"SendGrid エラー: {response.text}")
                    raise Exception(f"SendGrid API error: {response.status_code}")
                
            except Exception as e:
                print(f"メール送信エラー: {str(e)}")
                print(f"エラーの種類: {type(e).__name__}")
                import traceback
                print(traceback.format_exc())
                # エラーが発生しても、セキュリティのためユーザーには通知しない
        
        # セキュリティのため、ユーザーが存在するかどうかに関わらず同じメッセージを表示
        flash('パスワードリセットの手順をメールで送信しました。メールをご確認ください。', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('forgot_password.html')

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """パスワードリセットページ"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    # トークンからユーザーを検索
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        flash('無効または期限切れのリンクです。もう一度パスワードリセットをリクエストしてください。', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # 入力チェック
        if not password or not confirm_password:
            flash('すべての項目を入力してください。', 'danger')
            return render_template('reset_password.html', token=token)
        
        # パスワードの一致チェック
        if password != confirm_password:
            flash('パスワードが一致しません。', 'danger')
            return render_template('reset_password.html', token=token)
        
        # パスワードの強度チェック
        if len(password) < 8:
            flash('パスワードは8文字以上である必要があります。', 'danger')
            return render_template('reset_password.html', token=token)
        
        # パスワードの更新
        user.set_password(password)
        user.clear_reset_token()
        db.session.commit()
        
        flash('パスワードが更新されました。新しいパスワードでログインしてください。', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('reset_password.html', token=token) 