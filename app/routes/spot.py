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
            return render_template('spot_form.html', is_edit=False)
        
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
            rating=float(rating) if rating else None,
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
                            google_photo_reference=None,  # ユーザーアップロード写真なのでNULL
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
                        google_photo_reference=None,  # ユーザーアップロード写真なのでNULL
                        is_google_photo=False
                    )
                    db.session.add(photo_obj)
        
        # 手動アフィリエイトリンク処理
        rakuten_url = request.form.get('rakuten_url', '').strip()
        rakuten_active = 'rakuten_active' in request.form
        
        if rakuten_url:  # URL入力がある場合は手動設定を優先
            # 既存のリンクがあれば更新、なければ新規作成
            existing_link = AffiliateLink.query.filter_by(
                spot_id=spot.id, 
                platform='rakuten'
            ).first()
            
            if existing_link:
                # 既存リンクの更新
                existing_link.url = rakuten_url
                existing_link.title = '楽天トラベル'
                existing_link.description = '楽天トラベルで予約 (PRを含む)'
                existing_link.is_active = rakuten_active
            else:
                # 新規リンク作成
                affiliate_link = AffiliateLink(
                    spot_id=spot.id,
                    platform='rakuten',
                    url=rakuten_url,
                    title='楽天トラベル',
                    description='楽天トラベルで予約 (PRを含む)',
                    icon_key='rakuten-travel',
                    is_active=rakuten_active
                )
                db.session.add(affiliate_link)
            
            print(f"手動設定された楽天トラベルアフィリエイトリンクを作成/更新: {rakuten_url}")
            
        else:  # 手動入力がない場合
            # 既存のリンクがあれば、非アクティブに設定しURLも空にする
            existing_link = AffiliateLink.query.filter_by(
                spot_id=spot.id, 
                platform='rakuten'
            ).first()
            
            if existing_link:
                existing_link.is_active = False
                existing_link.url = ''  # URLを空にする
                print(f"既存の楽天トラベルアフィリエイトリンクを非アクティブに設定: ID={existing_link.id}")
            
            # 新規登録時のみ自動設定を行う
            # 楽天トラベルアフィリエイトリンクの自動生成
            if current_user.rakuten_affiliate_id and name:
                try:
                    print(f"楽天トラベルAPI検索: {name}")
                    # 楽天トラベルAPIを呼び出してホテル情報を取得
                    hotel_results = search_hotel(name, current_user.rakuten_affiliate_id)
                    
                    if 'error' not in hotel_results and 'hotels' in hotel_results and len(hotel_results['hotels']) > 0:
                        print(f"ホテル検索結果: {len(hotel_results['hotels'])}件見つかりました")
                        # ホテル情報を取得
                        for hotel_item in hotel_results['hotels']:
                            # 修正: hotel_item['hotel']はリスト型なのでインデックスでアクセス
                            if 'hotel' in hotel_item and len(hotel_item['hotel']) > 0:
                                # 最初の要素に 'hotelBasicInfo' が含まれている
                                hotel_info = hotel_item['hotel'][0]
                                if 'hotelBasicInfo' in hotel_info:
                                    basic_info = hotel_info['hotelBasicInfo']
                                    hotel_name = basic_info.get('hotelName', '')
                                    print(f"ホテル名: {hotel_name}")
                                    
                                    # 類似度チェックを撤廃し、最初に見つかったホテルを正とする
                                    print(f"類似度チェックをスキップし、最初のホテルを採用: {hotel_name}")
                                    
                                    # URLがある場合のみ処理
                                    if basic_info.get('hotelInformationUrl'):
                                        hotel_url = basic_info.get('hotelInformationUrl')
                                        print(f"ホテルURL: {hotel_url}")
                                        # アフィリエイトURLを生成
                                        affiliate_url = generate_rakuten_affiliate_url(
                                            hotel_url,
                                            current_user.rakuten_affiliate_id
                                        )
                                        print(f"アフィリエイトURL生成: {affiliate_url}")
                                        
                                        # 新規リンク作成
                                        affiliate_link = AffiliateLink(
                                            spot_id=spot.id,
                                            platform='rakuten',
                                            url=affiliate_url,
                                            title='楽天トラベル',
                                            description='楽天トラベルで予約 (PRを含む)',
                                            icon_key='rakuten-travel',
                                            is_active=True
                                        )
                                        db.session.add(affiliate_link)
                                        
                                        print(f"楽天トラベルアフィリエイトリンクを自動生成: スポット名={name}")
                                        break  # 最初の一致したホテルのみ使用
                except Exception as e:
                    print(f"楽天トラベルアフィリエイトリンク生成エラー: {str(e)}")
        
        db.session.commit()
        flash('スポットを追加しました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    return render_template('spot_form.html', is_edit=False)

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
        if rating:
            old_rating = spot.rating
            spot.rating = float(rating)
            # 新規評価の場合はreview_countを1に、既存評価の更新の場合はそのまま
            if old_rating is None:
                spot.review_count = 1
        else:
            spot.rating = None
            spot.review_count = 0
        
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
                            google_photo_reference=None,  # ユーザーアップロード写真なのでNULL
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
                        google_photo_reference=None,  # ユーザーアップロード写真なのでNULL
                        is_google_photo=False
                    )
                    db.session.add(photo_obj)
        
        # 手動アフィリエイトリンク処理
        rakuten_url = request.form.get('rakuten_url', '').strip()
        rakuten_active = 'rakuten_active' in request.form
        
        if rakuten_url:  # URL入力がある場合は手動設定を優先
            # 既存のリンクがあれば更新、なければ新規作成
            existing_link = AffiliateLink.query.filter_by(
                spot_id=spot.id, 
                platform='rakuten'
            ).first()
            
            if existing_link:
                # 既存リンクの更新
                existing_link.url = rakuten_url
                existing_link.title = '楽天トラベル'
                existing_link.description = '楽天トラベルで予約 (PRを含む)'
                existing_link.is_active = rakuten_active
            else:
                # 新規リンク作成
                affiliate_link = AffiliateLink(
                    spot_id=spot.id,
                    platform='rakuten',
                    url=rakuten_url,
                    title='楽天トラベル',
                    description='楽天トラベルで予約 (PRを含む)',
                    icon_key='rakuten-travel',
                    is_active=rakuten_active
                )
                db.session.add(affiliate_link)
            
            print(f"手動設定された楽天トラベルアフィリエイトリンクを作成/更新: {rakuten_url}")
            
        else:  # 手動入力がない場合
            # 既存のリンクがあれば、非アクティブに設定しURLも空にする
            existing_link = AffiliateLink.query.filter_by(
                spot_id=spot.id, 
                platform='rakuten'
            ).first()
            
            if existing_link:
                existing_link.is_active = False
                existing_link.url = ''  # URLを空にする
                print(f"既存の楽天トラベルアフィリエイトリンクを非アクティブに設定: ID={existing_link.id}")
            
            # 編集時は自動設定を行わない
        
        db.session.commit()
        flash('スポット情報を更新しました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    # ユーザーがアップロードした写真のみを取得（Google写真は除外）
    photos = Photo.query.filter_by(spot_id=spot_id, is_google_photo=False).all()

    # 楽天アフィリエイトリンクを明示的に取得
    rakuten_link = AffiliateLink.query.filter_by(
        spot_id=spot_id, 
        platform='rakuten'
    ).first()

    # デバッグログの追加
    if rakuten_link:
        print(f"テンプレートに渡す楽天アフィリエイトリンク: ID={rakuten_link.id}, URL={rakuten_link.url}")
    else:
        print("テンプレートに渡す楽天アフィリエイトリンク: なし")

    return render_template('spot_form.html', spot=spot, photos=photos, is_edit=True, rakuten_link=rakuten_link)

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
        
        # スポットの削除（関連するオブジェクトはcascadeで削除）
        db.session.delete(spot)
        db.session.commit()
        
        flash('スポットを削除しました。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'スポットの削除中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('profile.mypage')) 