from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from werkzeug.urls import url_parse

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