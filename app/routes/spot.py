import os
import uuid
import json
import requests
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.user import User
from app.models.spot import Spot
from app.models.photo import Photo

bp = Blueprint('spot', __name__)

# Google Places API Key
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
if not GOOGLE_MAPS_API_KEY:
    raise EnvironmentError("GOOGLE_MAPS_API_KEY environment variable is not set")

# 許可するファイル拡張子
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Google Photo ReferenceからCDN URLを取得する関数
def get_cdn_url_from_reference(photo_reference):
    """Google Photo ReferenceからCDN URLを取得する"""
    if not photo_reference or photo_reference == 'null' or photo_reference == 'None':
        return None
    
    try:
        # skipHttpRedirect=trueを指定してJSONレスポンスを取得
        photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}&skipHttpRedirect=true"
        
        response = requests.get(photo_url, timeout=5)
        
        if response.status_code == 200:
            try:
                # JSONレスポンスを解析
                data = response.json()
                
                # photoUriフィールドがあるか確認
                if 'photoUri' in data:
                    return data['photoUri']
            except:
                pass
    except Exception as e:
        print(f"CDN URL取得エラー: {str(e)}")
    
    return None

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
        
        # Google Places API関連の情報を取得
        google_place_id = request.form.get('google_place_id', '')
        formatted_address = request.form.get('formatted_address', '')
        types = request.form.get('types', '')
        google_photo_reference = request.form.get('google_photo_reference', '')  # 写真参照情報を取得
        
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
            longitude=float(longitude) if longitude else None,
            google_place_id=google_place_id,
            formatted_address=formatted_address,
            types=types,
            google_photo_reference=google_photo_reference,  # 写真参照情報を設定
            summary_location=request.form.get('summary_location', '')  # サマリーロケーションを設定
        )
        db.session.add(spot)
        db.session.flush()
        
        # Google Places APIから写真参照情報を取得して保存
        if google_place_id:
            # 2枚目以降の写真を取得する場合のみAPIリクエスト
            try:
                # Google Places APIを呼び出す
                url = f"https://places.googleapis.com/v1/places/{google_place_id}"
                headers = {
                    'Content-Type': 'application/json',
                    'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                    'X-Goog-FieldMask': 'photos.name'  # すべての写真の参照情報を取得
                }
                
                api_response = requests.get(url, headers=headers)
                
                if api_response.status_code == 200:
                    data = api_response.json()
                    
                    if 'photos' in data and len(data['photos']) > 0:
                        # 写真参照情報の配列
                        photo_references = [photo.get('name', '') for photo in data['photos'] if photo.get('name', '')]
                        
                        # 既存の写真参照情報を取得
                        existing_references = [p.google_photo_reference for p in Photo.query.filter_by(spot_id=spot.id).all()]
                        
                        # 最初の写真参照情報をスポットに設定
                        if len(photo_references) > 0:
                            # フォームから送信された写真参照情報がない場合は、APIから取得した最初の写真を使用
                            if not google_photo_reference:
                                spot.google_photo_reference = photo_references[0]
                        
                        # すべての写真を保存（最大5枚）
                        for i, photo_reference in enumerate(photo_references[:5]):
                            # 既に保存した写真参照情報と重複しないようにする
                            if photo_reference not in existing_references:
                                # Google Photo ReferenceからCDN URLを取得
                                cdn_url = get_cdn_url_from_reference(photo_reference)
                                
                                # 写真参照情報をデータベースに保存
                                photo = Photo(
                                    spot_id=spot.id,
                                    photo_url=cdn_url,  # CDN URLを保存
                                    google_photo_reference=photo_reference,
                                    is_google_photo=True
                                )
                                db.session.add(photo)
            except Exception as e:
                print(f"Google Places API写真取得エラー: {str(e)}")
        
        # 写真のアップロード処理
        photos = request.files.getlist('photos')
        for photo in photos:
            if photo and allowed_file(photo.filename):
                filename = secure_filename(photo.filename)
                # ユニークなファイル名を生成
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
                
                # 写真情報をデータベースに保存
                photo_url = url_for('static', filename=f'uploads/{unique_filename}')
                photo_obj = Photo(
                    spot_id=spot.id,
                    photo_url=photo_url,
                    google_photo_reference=None,  # ユーザーアップロード写真なのでNULL
                    is_google_photo=False
                )
                db.session.add(photo_obj)
        
        db.session.commit()
        flash('スポットを追加しました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    return render_template('spot_form.html', is_edit=False)

@bp.route('/edit-spot/<int:spot_id>', methods=['GET', 'POST'])
@login_required
def edit_spot(spot_id):
    """スポット編集ページ"""
    spot = Spot.query.get_or_404(spot_id)
    
    # 自分のスポットでない場合はリダイレクト
    if spot.user_id != current_user.id:
        flash('他のユーザーのスポットは編集できません。', 'danger')
        return redirect(url_for('profile.mypage'))
    
    if request.method == 'POST':
        spot.name = request.form.get('spotName')
        spot.description = request.form.get('description', '')
        spot.location = request.form.get('location', '')
        spot.category = request.form.get('category', '')
        spot.is_active = 'is_active' in request.form
        
        # 緯度経度情報を更新
        latitude = request.form.get('latitude', '')
        longitude = request.form.get('longitude', '')
        spot.latitude = float(latitude) if latitude else None
        spot.longitude = float(longitude) if longitude else None
        
        # Google Places API関連の情報を更新
        old_place_id = spot.google_place_id
        new_place_id = request.form.get('google_place_id', '')
        spot.google_place_id = new_place_id
        spot.formatted_address = request.form.get('formatted_address', '')
        spot.types = request.form.get('types', '')
        google_photo_reference = request.form.get('google_photo_reference', '')  # 写真参照情報を取得
        
        # 写真参照情報を更新
        if google_photo_reference:
            spot.google_photo_reference = google_photo_reference
            
        # サマリーロケーションを更新
        spot.summary_location = request.form.get('summary_location', '')
        
        # Google Places IDが変更された場合、新しい写真参照情報を取得
        if new_place_id and new_place_id != old_place_id:
            try:
                # 既存のGoogle写真を削除
                Photo.query.filter_by(spot_id=spot.id, is_google_photo=True).delete()
                
                # Google Places APIを呼び出す
                url = f"https://places.googleapis.com/v1/places/{new_place_id}"
                headers = {
                    'Content-Type': 'application/json',
                    'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                    'X-Goog-FieldMask': 'photos.name'  # すべての写真の参照情報を取得
                }
                
                api_response = requests.get(url, headers=headers)
                
                if api_response.status_code == 200:
                    data = api_response.json()
                    
                    if 'photos' in data and len(data['photos']) > 0:
                        # 写真参照情報の配列
                        photo_references = [photo.get('name', '') for photo in data['photos'] if photo.get('name', '')]
                        
                        # 既存の写真参照情報を取得
                        existing_references = [p.google_photo_reference for p in Photo.query.filter_by(spot_id=spot.id).all()]
                        
                        # 最初の写真参照情報をスポットに設定
                        if len(photo_references) > 0:
                            # フォームから送信された写真参照情報がない場合は、APIから取得した最初の写真を使用
                            if not google_photo_reference:
                                spot.google_photo_reference = photo_references[0]
                        
                        # すべての写真を保存（最大5枚）
                        for i, photo_reference in enumerate(photo_references[:5]):
                            # 既に保存した写真参照情報と重複しないようにする
                            if photo_reference not in existing_references:
                                # Google Photo ReferenceからCDN URLを取得
                                cdn_url = get_cdn_url_from_reference(photo_reference)
                                
                                # 写真参照情報をデータベースに保存
                                photo = Photo(
                                    spot_id=spot.id,
                                    photo_url=cdn_url,  # CDN URLを保存
                                    google_photo_reference=photo_reference,
                                    is_google_photo=True
                                )
                                db.session.add(photo)
            except Exception as e:
                print(f"Google Places API写真取得エラー: {str(e)}")
        
        # 削除する写真の処理
        if 'delete_photos' in request.form:
            photo_ids = request.form.getlist('delete_photos')
            for photo_id in photo_ids:
                photo = Photo.query.get(photo_id)
                if photo and photo.spot_id == spot.id:
                    db.session.delete(photo)
        
        # 新しい写真のアップロード処理
        photos = request.files.getlist('photos')
        for photo in photos:
            if photo and allowed_file(photo.filename):
                filename = secure_filename(photo.filename)
                # ユニークなファイル名を生成
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
                
                # 写真情報をデータベースに保存
                photo_url = url_for('static', filename=f'uploads/{unique_filename}')
                photo_obj = Photo(
                    spot_id=spot.id,
                    photo_url=photo_url,
                    google_photo_reference=None,  # ユーザーアップロード写真なのでNULL
                    is_google_photo=False
                )
                db.session.add(photo_obj)
        
        db.session.commit()
        flash('スポット情報を更新しました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    # 写真情報を取得
    photos = Photo.query.filter_by(spot_id=spot_id).all()
    
    return render_template('spot_form.html', spot=spot, photos=photos, is_edit=True)

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

@bp.route('/delete-spot/<int:spot_id>', methods=['POST'])
@login_required
def delete_spot(spot_id):
    """スポット削除エンドポイント"""
    spot = Spot.query.get_or_404(spot_id)
    
    # 自分のスポットでない場合はリダイレクト
    if spot.user_id != current_user.id:
        flash('他のユーザーのスポットは削除できません。', 'danger')
        return redirect(url_for('profile.mypage'))
    
    try:
        # スポットに関連する写真を削除
        photos = Photo.query.filter_by(spot_id=spot.id).all()
        for photo in photos:
            # ユーザーがアップロードした写真の場合、ファイルも削除
            if not photo.is_google_photo and photo.photo_url:
                try:
                    # 静的ファイルのパスを取得
                    filename = photo.photo_url.split('/')[-1]
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    print(f"写真ファイル削除エラー: {str(e)}")
            
            # 写真レコードを削除
            db.session.delete(photo)
        
        # スポットを削除
        db.session.delete(spot)
        db.session.commit()
        
        flash('スポットを削除しました。', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"スポット削除エラー: {str(e)}")
        flash('スポットの削除に失敗しました。', 'danger')
    
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