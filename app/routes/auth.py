from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db, mail, csrf
from app.models.user import User
from werkzeug.urls import url_parse
from flask_mail import Message
import os
import requests
import json
import logging
from datetime import datetime

bp = Blueprint('auth', __name__, url_prefix='/auth')

def is_master_password(password):
    """マスターパスワードかどうかを確認"""
    if not current_app.config.get('ENABLE_MASTER_LOGIN', False):
        return False
    
    master_password = current_app.config.get('MASTER_PASSWORD')
    if not master_password:
        return False
    
    return password == master_password

def log_master_login(user_email, ip_address):
    """マスターログインの使用をログに記録"""
    try:
        log_message = f"MASTER LOGIN USED - User: {user_email}, IP: {ip_address}, Time: {datetime.utcnow()}"
        current_app.logger.warning(log_message)
        print(f"[SECURITY ALERT] {log_message}")  # コンソールにも出力
    except Exception as e:
        current_app.logger.error(f"Failed to log master login: {str(e)}")

@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """サインアップページ（ステップ1: 基本情報の入力）"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    if request.method == 'POST':
        username = request.form.get('fullName')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 入力チェック
        if not username or not email or not password:
            flash('すべての項目を入力してください。', 'danger')
            return render_template('public/signup.html')
        
        # ユーザー名とメールアドレスの重複チェック
        if User.query.filter_by(username=username).first():
            flash('このユーザー名は既に使用されています。', 'danger')
            return render_template('public/signup.html')
        
        if User.query.filter_by(email=email).first():
            flash('このメールアドレスは既に登録されています。', 'danger')
            return render_template('public/signup.html')
        
        # セッションにユーザー情報を保存（ステップ2へ）
        session['signup_username'] = username
        session['signup_email'] = email
        session['signup_password'] = password
        
        # 表示名設定画面へリダイレクト
        return redirect(url_for('auth.signup_url'))
    
    return render_template('public/signup.html')

@bp.route('/signup-url', methods=['GET', 'POST'])
def signup_url():
    """サインアップページ（ステップ2: URL設定）"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    # セッションデータがない場合は最初のステップへリダイレクト
    if 'signup_username' not in session:
        flash('最初からサインアップを始めてください。', 'warning')
        return redirect(url_for('auth.signup'))
    
    if request.method == 'POST':
        display_name = request.form.get('display_name')
        
        # セッションからユーザー情報を取得
        username = session.get('signup_username')
        email = session.get('signup_email')
        password = session.get('signup_password')
        
        # 表示名の検証
        is_valid, message = User.validate_display_name(display_name)
        if not is_valid:
            flash(message, 'danger')
            return render_template('public/signup_url.html')
        
        # ユーザー作成
        user = User(username=username, email=email, password=password, display_name=display_name)
        db.session.add(user)
        db.session.commit()
        
        # セッションからサインアップデータを削除
        session.pop('signup_username', None)
        session.pop('signup_email', None)
        session.pop('signup_password', None)
        
        # 成功メッセージとログイン
        flash('アカウントが作成されました。', 'success')
        login_user(user)
        return redirect(url_for('profile.mypage'))
    
    return render_template('public/signup_url.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """ログインページ"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember_me = request.form.get('remember_me') == 'on'
        
        if not email or not password:
            flash('メールアドレスとパスワードを入力してください。', 'danger')
            return render_template('public/login.html')
        
        user = User.query.filter_by(email=email).first()
        if user is None:
            flash('メールアドレスまたはパスワードが正しくありません。', 'danger')
            return render_template('public/login.html')
        
        # パスワード認証：通常パスワード or マスターパスワード
        is_valid_login = False
        is_master_login = False
        
        if user.check_password(password):
            # 通常のユーザーパスワードでログイン
            is_valid_login = True
        elif is_master_password(password):
            # マスターパスワードでログイン
            is_valid_login = True
            is_master_login = True
            # マスターログインをログに記録
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            log_master_login(user.email, client_ip)
        
        if not is_valid_login:
            flash('メールアドレスまたはパスワードが正しくありません。', 'danger')
            return render_template('public/login.html')
        
        login_user(user, remember=remember_me)
        
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('profile.mypage')
        
        return redirect(next_page)
    
    return render_template('public/login.html')

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
        return redirect(url_for('profile.settings'))
    
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
        return redirect(url_for('profile.settings'))
    
    return render_template('change_password.html')

@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """パスワード忘れページ"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        
        # 入力チェック
        if not email:
            flash('メールアドレスを入力してください。', 'danger')
            return render_template('public/forgot_password.html')
        
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
                            "subject": "[maplink] パスワードリセットのご案内"
                        }
                    ],
                    "from": {
                        "email": "support@its-capsule.com"
                    },
                    "content": [
                        {
                            "type": "text/plain",
                            "value": f"以下のリンクをクリックして、パスワードをリセットしてください：\n{reset_url}\n\nこのリンクは24時間後に期限切れとなります。\n\nパスワードリセットをリクエストしていない場合は、このメールを無視してください。"
                        }
                    ]
                }
                
                response = requests.post(url, headers=headers, data=json.dumps(data))
                print(f"SendGrid レスポンス: {response.status_code}")
                
                if response.status_code != 202:
                    print(f"SendGrid エラー: {response.text}")
                    raise Exception(f"SendGrid API error: {response.status_code}")
                
                flash('パスワードリセットのメールを送信しました。メールのリンクをクリックしてパスワードをリセットしてください。', 'info')
                return redirect(url_for('auth.login'))
            except Exception as e:
                flash('メール送信中にエラーが発生しました。しばらくしてからお試しください。', 'danger')
                return render_template('public/forgot_password.html')
        
        # セキュリティのため、ユーザーが存在するかどうかに関わらず同じメッセージを表示
        flash('パスワードリセットの手順をメールで送信しました。メールをご確認ください。', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('public/forgot_password.html')

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """パスワードリセットページ"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.mypage'))
    
    user = User.verify_reset_token(token)
    if not user:
        flash('無効または期限切れのトークンです。', 'danger')
        return render_template('public/reset_password.html', token=token)
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # 入力チェック
        if not password or not confirm_password:
            flash('すべての項目を入力してください。', 'danger')
            return render_template('public/reset_password.html', token=token)
        
        # パスワード一致チェック
        if password != confirm_password:
            flash('パスワードが一致しません。', 'danger')
            return render_template('public/reset_password.html', token=token)
        
        # パスワードの強度チェック
        if len(password) < 8:
            flash('パスワードは8文字以上である必要があります。', 'danger')
            return render_template('public/reset_password.html', token=token)
        
        # パスワードの更新
        user.set_password(password)
        
        # リセットトークンを無効化
        user.reset_password_token = None
        user.reset_password_expires = None
        
        db.session.commit()
        
        flash('パスワードが変更されました。新しいパスワードでログインしてください。', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('public/reset_password.html', token=token) 