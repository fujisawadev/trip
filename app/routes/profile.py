import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.user import User
from app.models.spot import Spot

bp = Blueprint('profile', __name__)

# 許可するファイル拡張子
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/mypage')
@login_required
def mypage():
    """マイページ"""
    spots = Spot.query.filter_by(user_id=current_user.id).all()
    return render_template('mypage.html', user=current_user, spots=spots)

@bp.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """プロフィール編集ページ"""
    if request.method == 'POST':
        username = request.form.get('username')
        bio = request.form.get('bio')
        
        # ユーザー名の重複チェック（自分以外）
        if username != current_user.username and User.query.filter_by(username=username).first():
            flash('このユーザー名は既に使用されています。', 'danger')
            return render_template('edit_profile.html', user=current_user)
        
        # プロフィール画像のアップロード処理
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # ユーザーIDをファイル名に含める
                filename = f"{current_user.id}_{filename}"
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # データベースに保存するパスは相対パス
                relative_path = os.path.join('uploads', filename)
                current_user.profile_pic_url = relative_path
        
        # ユーザー情報の更新
        current_user.username = username
        current_user.bio = bio
        db.session.commit()
        
        flash('プロフィールが更新されました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    return render_template('edit_profile.html', user=current_user)

@bp.route('/settings')
@login_required
def settings():
    """設定ページ"""
    return render_template('settings.html')

@bp.route('/settings/sns')
@login_required
def sns_settings():
    """SNS連携設定ページ"""
    return render_template('sns.html')

@bp.route('/user/<username>')
def user_profile(username):
    """ユーザープロフィールページ"""
    user = User.query.filter_by(username=username).first_or_404()
    spots = Spot.query.filter_by(user_id=user.id).all()
    return render_template('public/profile.html', user=user, spots=spots) 