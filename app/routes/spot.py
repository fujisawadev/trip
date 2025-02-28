import os
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.user import User
from app.models.spot import Spot
from app.models.photo import Photo

bp = Blueprint('spot', __name__)

# 許可するファイル拡張子
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/add-spot', methods=['GET', 'POST'])
@login_required
def add_spot():
    """スポット追加ページ"""
    if request.method == 'POST':
        name = request.form.get('spotName')
        description = request.form.get('description', '')
        location = request.form.get('location', '')
        category = request.form.get('category', '')
        is_active = 'is_active' in request.form
        
        # 緯度経度情報を取得
        latitude = request.form.get('latitude', '')
        longitude = request.form.get('longitude', '')
        
        # 入力チェック
        if not name:
            flash('スポット名を入力してください。', 'danger')
            return render_template('spot_form.html', is_edit=False)
        
        # スポット作成
        spot = Spot(
            user_id=current_user.id,
            name=name,
            description=description,
            location=location,
            category=category,
            is_active=is_active,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None
        )
        db.session.add(spot)
        db.session.flush()  # IDを取得するためにフラッシュ
        
        # 写真のアップロード処理
        if 'photos' in request.files:
            files = request.files.getlist('photos')
            for file in files:
                if file and file.filename != '' and allowed_file(file.filename):
                    # ユニークなファイル名を生成
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(file_path)
                    
                    # データベースに保存するパスは相対パス
                    relative_path = os.path.join('uploads', unique_filename)
                    photo = Photo(spot_id=spot.id, photo_url=relative_path)
                    db.session.add(photo)
        
        db.session.commit()
        
        flash('スポットが追加されました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    return render_template('spot_form.html', is_edit=False)

@bp.route('/edit-spot/<int:spot_id>', methods=['GET', 'POST'])
@login_required
def edit_spot(spot_id):
    """スポット編集ページ"""
    spot = Spot.query.filter_by(id=spot_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        name = request.form.get('spotName')
        description = request.form.get('description', '')
        location = request.form.get('location', '')
        category = request.form.get('category', '')
        is_active = 'is_active' in request.form
        
        # 緯度経度情報を取得
        latitude = request.form.get('latitude', '')
        longitude = request.form.get('longitude', '')
        
        # 入力チェック
        if not name:
            flash('スポット名を入力してください。', 'danger')
            return render_template('spot_form.html', is_edit=True, spot=spot)
        
        # スポット更新
        spot.name = name
        spot.description = description
        spot.location = location
        spot.category = category
        spot.is_active = is_active
        spot.latitude = float(latitude) if latitude else None
        spot.longitude = float(longitude) if longitude else None
        
        # 削除する写真の処理
        if 'delete_photos' in request.form:
            photo_ids = request.form.getlist('delete_photos')
            for photo_id in photo_ids:
                photo = Photo.query.get(photo_id)
                if photo and photo.spot_id == spot.id:
                    db.session.delete(photo)
        
        # 写真のアップロード処理
        if 'photos' in request.files:
            files = request.files.getlist('photos')
            for file in files:
                if file and file.filename != '' and allowed_file(file.filename):
                    # ユニークなファイル名を生成
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(file_path)
                    
                    # データベースに保存するパスは相対パス
                    relative_path = os.path.join('uploads', unique_filename)
                    photo = Photo(spot_id=spot.id, photo_url=relative_path)
                    db.session.add(photo)
        
        db.session.commit()
        
        flash('スポットが更新されました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    return render_template('spot_form.html', is_edit=True, spot=spot)

@bp.route('/toggle-spot/<int:spot_id>')
@login_required
def toggle_spot(spot_id):
    """スポットの有効/無効を切り替える"""
    spot = Spot.query.filter_by(id=spot_id, user_id=current_user.id).first_or_404()
    spot.is_active = not spot.is_active
    db.session.commit()
    
    status = '有効' if spot.is_active else '無効'
    flash(f'スポット「{spot.name}」を{status}にしました。', 'success')
    return redirect(url_for('profile.mypage'))

@bp.route('/delete-spot/<int:spot_id>')
@login_required
def delete_spot(spot_id):
    """スポットを削除する"""
    spot = Spot.query.filter_by(id=spot_id, user_id=current_user.id).first_or_404()
    
    # 関連する写真も削除される（cascade設定済み）
    db.session.delete(spot)
    db.session.commit()
    
    flash(f'スポット「{spot.name}」を削除しました。', 'success')
    return redirect(url_for('profile.mypage'))

@bp.route('/<spot_id>/<username>')
def spot_detail(spot_id, username):
    """スポット詳細ページ（公開）"""
    user = User.query.filter_by(username=username).first_or_404()
    spot = Spot.query.filter_by(id=spot_id, user_id=user.id, is_active=True).first_or_404()
    # スポットに関連する写真を取得
    photos = Photo.query.filter_by(spot_id=spot_id).all()
    return render_template('public/spot_detail.html', spot=spot, user=user, photos=photos)

@bp.route('/spot/<spot_id>')
def spot_detail_simple(spot_id):
    """スポット詳細ページ（シンプルURL）"""
    spot = Spot.query.filter_by(id=spot_id, is_active=True).first_or_404()
    user = User.query.filter_by(id=spot.user_id).first_or_404()
    # スポットに関連する写真を取得
    photos = Photo.query.filter_by(spot_id=spot_id).all()
    return render_template('public/spot_detail.html', spot=spot, user=user, photos=photos) 