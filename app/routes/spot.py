import os
import uuid
import json
import requests
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.user import User
from app.models.spot import Spot
from app.models.photo import Photo
from app.models.affiliate_link import AffiliateLink
from app.models.social_post import SocialPost
from app.utils.s3_utils import upload_file_to_s3, delete_file_from_s3
from app.utils.rakuten_api import search_hotel, generate_rakuten_affiliate_url
from sqlalchemy.orm import joinedload
from app.services.google_photos import get_google_photos_by_place_id

bp = Blueprint('spot', __name__)

# Google Places API Key
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
if not GOOGLE_MAPS_API_KEY:
    raise EnvironmentError("GOOGLE_MAPS_API_KEY environment variable is not set")

# 許可するファイル拡張子
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _update_social_links(spot_id, form_data):
    """SNSリンクを更新または作成/削除するヘルパー関数"""
    platforms = ['instagram', 'tiktok', 'twitter', 'youtube']
    for platform in platforms:
        url = form_data.get(f'{platform}_url', '').strip()
        
        # 既存の投稿を検索
        existing_post = SocialPost.query.filter_by(
            spot_id=spot_id, 
            platform=platform,
            user_id=current_user.id
        ).first()
        
        if url:
            # URLが入力されている場合
            if existing_post:
                # 既存の投稿を更新
                existing_post.post_url = url
            else:
                # 新しい投稿を作成
                new_post = SocialPost(
                    spot_id=spot_id,
                    user_id=current_user.id,
                    platform=platform,
                    post_url=url
                )
                db.session.add(new_post)
        elif existing_post:
            # URLが空で、既存の投稿がある場合は削除
            db.session.delete(existing_post)

def _update_other_links(spot_id, form_data):
    """任意追加された「その他のリンク」を更新するヘルパー関数"""
    # フォームから送信されたリンクを解析
    submitted_links = []
    index = 0
    while True:
        title_key = f'other_links[{index}][title]'
        url_key = f'other_links[{index}][url]'
        if title_key not in form_data and url_key not in form_data:
            break

        link_id_str = form_data.get(f'other_links[{index}][id]')
        title = form_data.get(title_key, '').strip()
        url = form_data.get(url_key, '').strip()
        
        # IDを整数に変換（'null'や空文字の場合も考慮）
        link_id = int(link_id_str) if link_id_str and link_id_str != 'null' else None
        
        submitted_links.append({'id': link_id, 'title': title, 'url': url})
        index += 1

    # 既存のカスタムリンクを取得
    existing_links = AffiliateLink.query.filter_by(spot_id=spot_id, platform='custom').all()
    existing_link_map = {link.id: link for link in existing_links}
    
    submitted_ids = set()

    # 送信されたリンクを処理 (更新または追加)
    for link_data in submitted_links:
        link_id = link_data.get('id')
        title = link_data.get('title')
        url = link_data.get('url')

        if not title or not url:
            continue

        if link_id and link_id in existing_link_map:
            # 既存リンクを更新
            link_to_update = existing_link_map[link_id]
            link_to_update.title = title
            link_to_update.url = url
            submitted_ids.add(link_id)
        else:
            # 新規リンクを追加
            new_link = AffiliateLink(
                spot_id=spot_id,
                platform='custom',
                title=title,
                url=url,
                description='外部サイトで詳細を確認 (PRを含む)',
                icon_key='link', # 汎用アイコンキー
                is_active=True
            )
            db.session.add(new_link)

    # フォームから削除されたリンクをDBから削除
    for link_id, link in existing_link_map.items():
        if link_id not in submitted_ids:
            # フォームに存在しなかった既存のリンクは削除
            if not any(sl['id'] is None and sl['title'] == link.title and sl['url'] == link.url for sl in submitted_links):
                 db.session.delete(link)

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
        # サマリーロケーションを取得
        summary_location = request.form.get('summary_location', '')
        
        # 評価データを取得
        rating = request.form.get('rating', '')
        
        # 入力チェック
        if not name:
            flash('スポット名を入力してください。', 'danger')
            return render_template('spot_form.html', is_edit=False, rakuten_link=None)
        
        # スポット作成
        spot = Spot(
            name=name,
            description=description,
            location=location,
            category=category,
            user_id=current_user.id,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            google_place_id=google_place_id,
            formatted_address=formatted_address,
            types=types,
            summary_location=summary_location,
            rating=float(rating) if rating else 0.0,
            review_count=1 if rating else 0,
            is_active=is_active
        )
        db.session.add(spot)
        db.session.flush()  # IDを確定するためにflush
        
        # 写真のアップロード処理 (ユーザーがアップロードした写真はこちらで処理される)
        photos = request.files.getlist('photos')
        for photo in photos:
            if photo and allowed_file(photo.filename):
                # ファイルサイズチェック（1枚あたり10MB制限）
                if photo.content_length and photo.content_length > current_app.config.get('SINGLE_FILE_SIZE_LIMIT', 10 * 1024 * 1024):
                    flash(f'写真「{photo.filename}」のサイズが大きすぎます（1枚あたり10MB以下）。', 'danger')
                    continue
                
                # ファイルを読み込んでサイズチェック（content_lengthが利用できない場合）
                photo.seek(0, 2)  # ファイルの最後に移動
                file_size = photo.tell()
                photo.seek(0)  # ファイルの先頭に戻す
                
                if file_size > current_app.config.get('SINGLE_FILE_SIZE_LIMIT', 10 * 1024 * 1024):
                    file_size_mb = file_size / (1024 * 1024)
                    flash(f'写真「{photo.filename}」のサイズが大きすぎます（{file_size_mb:.1f}MB）。1枚あたり10MB以下の画像をお選びください。', 'danger')
                    continue
                # S3が有効かチェック
                if current_app.config.get('USE_S3', False):
                    # S3にアップロード (spot_photoフォルダに保存)
                    photo_url = upload_file_to_s3(photo, folder='spot_photo')
                    
                    # アップロードに成功した場合のみ処理
                    if photo_url:
                        photo_obj = Photo(
                            spot_id=spot.id,
                            photo_url=photo_url,
                            is_google_photo=False
                        )
                        db.session.add(photo_obj)
                    else:
                        flash(f'写真「{photo.filename}」のアップロードに失敗しました。', 'danger')
                else:
                    # 従来のローカルストレージにアップロード
                    filename = secure_filename(photo.filename)
                    # ユニークなファイル名を生成
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
                    
                    # 写真情報をデータベースに保存
                    photo_url = url_for('static', filename=f'uploads/{unique_filename}')
                    photo_obj = Photo(
                        spot_id=spot.id,
                        photo_url=photo_url,
                        is_google_photo=False
                    )
                    db.session.add(photo_obj)
        
        # --- 楽天トラベル アフィリエイトリンク処理 ---
        rakuten_url = request.form.get('rakuten_url', '').strip()

        if rakuten_url:
            # 手動URLが入力されていれば、それを保存
            affiliate_link = AffiliateLink(
                spot_id=spot.id,
                platform='rakuten',
                url=rakuten_url,
                title='楽天トラベル',
                description='楽天トラベルで予約 (PRを含む)',
                icon_key='rakuten-travel',
                is_active=True # URLがあれば常にアクティブ
            )
            db.session.add(affiliate_link)
            print(f"手動で楽天トラベルリンクを追加: {rakuten_url}")
        

        # SNSリンクの更新
        _update_social_links(spot.id, request.form)

        # その他のリンクの更新
        _update_other_links(spot.id, request.form)

        db.session.commit()
        flash('スポットを追加しました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    return render_template('spot_form.html', is_edit=False, rakuten_link=None, custom_links=[])

@bp.route('/edit-spot/<int:spot_id>', methods=['GET', 'POST'])
@login_required
def edit_spot(spot_id):
    """スポット編集ページ"""
    # アフィリエイトリンクを積極的に読み込む
    spot = Spot.query.options(joinedload(Spot.affiliate_links)).filter_by(id=spot_id, user_id=current_user.id).first_or_404()
    
    # デバッグログの追加
    rakuten_links = [link for link in spot.affiliate_links if link.platform == 'rakuten']
    print(f"編集前の楽天アフィリエイトリンク: {[(link.id, link.url) for link in rakuten_links]}")
    
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
        
        # サマリーロケーションを更新
        spot.summary_location = request.form.get('summary_location', '')
        
        # 評価データを更新
        rating = request.form.get('rating', '')
        spot.rating = float(rating) if rating else 0.0
        
        # Google Places IDが変更された場合、関連する古いGoogle提供の写真を削除する
        if new_place_id and new_place_id != old_place_id:
            # 既存のGoogle提供の写真を削除
            Photo.query.filter_by(spot_id=spot.id, is_google_photo=True).delete()
        
        # 削除する写真の処理
        if 'delete_photos' in request.form:
            photo_ids = request.form.getlist('delete_photos')
            for photo_id in photo_ids:
                photo = Photo.query.get(photo_id)
                if photo and photo.spot_id == spot.id:
                    # S3が有効で、ユーザーアップロード写真の場合、S3からも削除
                    if current_app.config.get('USE_S3', False) and not photo.is_google_photo:
                        delete_file_from_s3(photo.photo_url)
                    # データベースから削除
                    db.session.delete(photo)
        
        # 新しい写真のアップロード処理
        photos = request.files.getlist('photos')
        for photo in photos:
            if photo and allowed_file(photo.filename):
                # ファイルサイズチェック（1枚あたり10MB制限）
                if photo.content_length and photo.content_length > current_app.config.get('SINGLE_FILE_SIZE_LIMIT', 10 * 1024 * 1024):
                    flash(f'写真「{photo.filename}」のサイズが大きすぎます（1枚あたり10MB以下）。', 'danger')
                    continue
                
                # ファイルを読み込んでサイズチェック（content_lengthが利用できない場合）
                photo.seek(0, 2)  # ファイルの最後に移動
                file_size = photo.tell()
                photo.seek(0)  # ファイルの先頭に戻す
                
                if file_size > current_app.config.get('SINGLE_FILE_SIZE_LIMIT', 10 * 1024 * 1024):
                    file_size_mb = file_size / (1024 * 1024)
                    flash(f'写真「{photo.filename}」のサイズが大きすぎます（{file_size_mb:.1f}MB）。1枚あたり10MB以下の画像をお選びください。', 'danger')
                    continue
                # S3が有効かチェック
                if current_app.config.get('USE_S3', False):
                    # S3にアップロード (spot_photoフォルダに保存)
                    photo_url = upload_file_to_s3(photo, folder='spot_photo')
                    
                    # アップロードに成功した場合のみ処理
                    if photo_url:
                        photo_obj = Photo(
                            spot_id=spot.id,
                            photo_url=photo_url,
                            is_google_photo=False
                        )
                        db.session.add(photo_obj)
                    else:
                        flash(f'写真「{photo.filename}」のアップロードに失敗しました。', 'danger')
                else:
                    # 従来のローカルストレージにアップロード
                    filename = secure_filename(photo.filename)
                    # ユニークなファイル名を生成
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
                    
                    # 写真情報をデータベースに保存
                    photo_url = url_for('static', filename=f'uploads/{unique_filename}')
                    photo_obj = Photo(
                        spot_id=spot.id,
                        photo_url=photo_url,
                        is_google_photo=False
                    )
                    db.session.add(photo_obj)
        
        # --- 楽天トラベル アフィリエイトリンク処理 ---
        rakuten_url = request.form.get('rakuten_url', '').strip()
        existing_link = AffiliateLink.query.filter_by(
            spot_id=spot.id,
            platform='rakuten'
        ).first()

        if rakuten_url:
            # URLが入力されている場合、既存のリンクを更新または新規作成
            if existing_link:
                existing_link.url = rakuten_url
                existing_link.is_active = True
                print(f"楽天トラベルリンクを更新: {rakuten_url}")
            else:
                new_link = AffiliateLink(
                    spot_id=spot.id,
                    platform='rakuten',
                    url=rakuten_url,
                    title='楽天トラベル',
                    description='楽天トラベルで予約 (PRを含む)',
                    icon_key='rakuten-travel',
                    is_active=True
                )
                db.session.add(new_link)
                print(f"楽天トラベルリンクを新規作成: {rakuten_url}")
        
        elif existing_link:
            # URLが空にされ、既存のリンクがある場合は削除
            db.session.delete(existing_link)
            print(f"楽天トラベルリンクを削除: ID={existing_link.id}")

        # SNSリンクの更新
        _update_social_links(spot.id, request.form)
        
        # その他のリンクの更新
        _update_other_links(spot.id, request.form)
        
        db.session.commit()
        flash('スポット情報を更新しました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    # ユーザーがアップロードした写真のみを取得（Google写真は除外）
    photos = Photo.query.filter_by(spot_id=spot_id, is_google_photo=False).all()

    # 楽天アフィリエイトリンクを明示的に取得
    rakuten_link = next((link for link in spot.affiliate_links if link.platform == 'rakuten'), None)

    # カスタムプラットフォームのアフィリエイトリンクを辞書形式で取得
    custom_links = [link.to_dict() for link in spot.affiliate_links if link.platform == 'custom']

    # デバッグログの追加
    if rakuten_link:
        print(f"テンプレートに渡す楽天アフィリエイトリンク: ID={rakuten_link.id}, URL={rakuten_link.url}")
    else:
        print("テンプレートに渡す楽天アフィリエイトリンク: なし")

    return render_template('spot_form.html', spot=spot, photos=photos, is_edit=True, rakuten_link=rakuten_link, custom_links=custom_links)

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

@bp.route('/<int:spot_id>/toggle_status', methods=['POST'])
@login_required
def toggle_spot_status(spot_id):
    """スポットの有効/無効をAjaxで切り替えるAPI"""
    spot = Spot.query.filter_by(id=spot_id, user_id=current_user.id).first_or_404()
    
    # リクエストからJSONデータを取得
    data = request.get_json()
    if data and 'is_active' in data:
        spot.is_active = data['is_active']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'spot_id': spot.id,
            'is_active': spot.is_active
        })
    
    return jsonify({
        'success': False,
        'error': 'Invalid request data'
    }), 400

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
        # 関連する写真の削除処理
        photos = Photo.query.filter_by(spot_id=spot.id).all()
        for photo in photos:
            # S3が有効で、ユーザーアップロード写真の場合、S3からも削除
            if current_app.config.get('USE_S3', False) and not photo.is_google_photo and photo.photo_url:
                delete_file_from_s3(photo.photo_url)
            elif not photo.is_google_photo and photo.photo_url:
                # ローカルファイルの場合は静的ファイルから削除（コメント部分のユースケースのため残しています）
                try:
                    # ファイルパスを取得（/static/uploads/filename.jpg形式）
                    filename = photo.photo_url.split('/')[-1]
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    
                    # ファイルが存在するかチェック
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    print(f"ファイル削除エラー: {str(e)}")
        
        # スポットの削除（関連するオブジェクトはcascadeで削除されるが、明示的に削除）
        AffiliateLink.query.filter_by(spot_id=spot.id).delete()
        SocialPost.query.filter_by(spot_id=spot.id).delete()
        Photo.query.filter_by(spot_id=spot.id).delete()

        db.session.delete(spot)
        db.session.commit()
        
        flash('スポットを削除しました。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'スポットの削除中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('profile.mypage')) 