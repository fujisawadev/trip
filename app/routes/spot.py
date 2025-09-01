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
from app.services.google_places import get_place_review_summary
from app.models.spot_provider_id import SpotProviderId
from app.services.dataforseo import search_hotels as dfs_search_hotels
from app.utils.rakuten_api import search_hotel as rakuten_search
from app.services.rakuten_travel import fetch_detail_by_hotel_no as rakuten_fetch_detail
from app.services.rakuten_travel import simple_hotel_search_by_geo as rakuten_simple_geo

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
    """任意リンクをSpotの単一フィールドへ保存する（新仕様）"""
    title = (form_data.get('other_link_title') or '').strip()
    url = (form_data.get('other_link_url') or '').strip()
    spot = Spot.query.get(spot_id)
    if not spot:
        return
    spot.custom_link_title = title if title else None
    spot.custom_link_url = url if url else None

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
        # レビューサマリーを取得（フロントからのhidden）
        review_summary = request.form.get('review_summary', '')
        
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
            review_summary=review_summary or None,
            rating=float(rating) if rating else 0.0,
            review_count=1 if rating else 0,
            is_active=is_active
        )
        db.session.add(spot)
        db.session.flush()  # IDを確定するためにflush

        # DataForSEO: 宿泊系のみ・100m以内のときだけhotel_identifierを保存
        try:
            # 1) 宿泊系判定: spot.category / spot.types から判断
            def is_lodging_category(cat: str) -> bool:
                if not cat:
                    return False
                cat_l = cat.lower()
                keywords = ['hotel', 'hostel', 'inn', 'ryokan', 'lodging', '旅館', 'ホテル']
                return any(k in cat_l for k in ['hotel','hostel','inn','lodging']) or any(k in cat for k in ['旅館','ホテル'])

            lodging_ok = False
            if spot.category and is_lodging_category(spot.category):
                lodging_ok = True
            else:
                # types はJSON文字列またはカンマ区切りの可能性
                tval = spot.types
                try:
                    import json as _json
                    types_list = _json.loads(tval) if tval else []
                except Exception:
                    types_list = [s.strip() for s in tval.split(',')] if tval else []
                for t in types_list:
                    if is_lodging_category(str(t)):
                        lodging_ok = True
                        break

            if not lodging_ok:
                raise Exception('not lodging category')

            keyword = spot.name
            location_name = current_app.config.get('DATAFORSEO_DEFAULT_LOCATION', 'Japan')
            language_code = current_app.config.get('DATAFORSEO_DEFAULT_LANGUAGE', 'ja')
            items = dfs_search_hotels(
                keyword=keyword,
                location_name=location_name,
                language_code=language_code,
                currency=current_app.config.get('AGODA_CURRENCY', 'JPY'),
                adults=2,
            )
            chosen = None
            best_dist_m = None
            if items and spot.latitude and spot.longitude:
                import math
                def haversine_m(lat1, lon1, lat2, lon2):
                    R = 6371000.0
                    phi1 = math.radians(lat1)
                    phi2 = math.radians(lat2)
                    dphi = math.radians((lat2 - lat1))
                    dlambda = math.radians((lon2 - lon1))
                    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    return R * c
                for it in items:
                    loc = (it.get('location') or {})
                    lat = loc.get('latitude')
                    lng = loc.get('longitude')
                    if lat is None or lng is None:
                        continue
                    d_m = haversine_m(spot.latitude, spot.longitude, float(lat), float(lng))
                    if best_dist_m is None or d_m < best_dist_m:
                        best_dist_m = d_m
                        chosen = it
            # 100m以内のみ採用
            if chosen and best_dist_m is not None and best_dist_m <= 100 and chosen.get('hotel_identifier'):
                exists = SpotProviderId.query.filter_by(spot_id=spot.id, provider='dataforseo').first()
                if not exists:
                    mapping = SpotProviderId(
                        spot_id=spot.id,
                        provider='dataforseo',
                        external_id=chosen['hotel_identifier']
                    )
                    db.session.add(mapping)
        except Exception:
            # 宿泊系でない、または条件不一致は黙ってスキップ
            pass

        # 楽天トラベル: 宿泊系のみ・100m以内で hotelNo を保存
        try:
            def is_lodging_category(cat: str) -> bool:
                if not cat:
                    return False
                cat_l = cat.lower()
                keywords = ['hotel', 'hostel', 'inn', 'ryokan', 'lodging', '旅館', 'ホテル']
                return any(k in cat_l for k in ['hotel','hostel','inn','lodging']) or any(k in cat for k in ['旅館','ホテル'])

            lodging_ok = False
            if spot.category and is_lodging_category(spot.category):
                lodging_ok = True
            else:
                tval = spot.types
                try:
                    import json as _json
                    types_list = _json.loads(tval) if tval else []
                except Exception:
                    types_list = [s.strip() for s in tval.split(',')] if tval else []
                for t in types_list:
                    if is_lodging_category(str(t)):
                        lodging_ok = True
                        break
            # 施設名にもホテル系キーワードが含まれていれば許可
            if not lodging_ok and spot.name:
                name_l = spot.name.lower()
                if any(k in name_l for k in ['hotel','hostel','inn']) or ('ホテル' in spot.name or '旅館' in spot.name):
                    lodging_ok = True

            if not lodging_ok:
                raise Exception('not lodging category')

            hotels = []
            # 1) 緯度経度があれば SimpleHotelSearch を優先
            if spot.latitude and spot.longitude:
                geo_res = rakuten_simple_geo(spot.name, float(spot.latitude), float(spot.longitude), hits=5)
                if geo_res and isinstance(geo_res, dict):
                    # formatVersion 2 は二重配列
                    hotels = geo_res.get('hotels') or []
                    # 正規化: [{'hotel':[{'hotelBasicInfo':...}]}] 形式に合わせる
                    hotels = [ {'hotel':[h[0]]} for h in hotels if isinstance(h, list) and h ]
            # 2) フォールバックとしてキーワード検索
            if not hotels:
                rakuten_res = rakuten_search(spot.name, affiliate_id=current_app.config.get('RAKUTEN_AFFILIATE_ID'), hits=3)
                hotels = rakuten_res.get('hotels') if isinstance(rakuten_res, dict) else []
            if not hotels:
                raise Exception('no rakuten hotels')
            # 距離最小（100m以内）
            import math
            def haversine_m(lat1, lon1, lat2, lon2):
                R = 6371000.0
                phi1 = math.radians(lat1)
                phi2 = math.radians(lat2)
                dphi = math.radians((lat2 - lat1))
                dlambda = math.radians((lon2 - lon1))
                a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                return R * c
            best = None
            best_d = None
            for h in hotels:
                try:
                    basic = h['hotel'][0]['hotelBasicInfo'] if 'hotel' in h and h['hotel'] else {}
                    hlat = basic.get('latitude')
                    hlng = basic.get('longitude')
                    # 緯度経度が無い場合は詳細APIで補完
                    if (hlat is None or hlng is None) and basic.get('hotelNo'):
                        detail = rakuten_fetch_detail(str(basic.get('hotelNo')))
                        if detail and isinstance(detail, dict):
                            dhs = detail.get('hotels') or []
                            if dhs and isinstance(dhs[0], dict) and dhs[0].get('hotel'):
                                dinfo = dhs[0]['hotel'][0].get('hotelBasicInfo', {})
                                hlat = dinfo.get('latitude') or hlat
                                hlng = dinfo.get('longitude') or hlng
                    if hlat is None or hlng is None or not spot.latitude or not spot.longitude:
                        continue
                    d = haversine_m(float(spot.latitude), float(spot.longitude), float(hlat), float(hlng))
                    if best_d is None or d < best_d:
                        best_d = d
                        best = basic
                except Exception:
                    continue
            if best and best_d is not None and best_d <= 100 and best.get('hotelNo'):
                exists = SpotProviderId.query.filter_by(spot_id=spot.id, provider='rakuten').first()
                if not exists:
                    db.session.add(SpotProviderId(spot_id=spot.id, provider='rakuten', external_id=str(best['hotelNo'])))
        except Exception:
            pass

        # サーバ側フォールバック: hiddenが空で、place_id があればAPIから取得
        try:
            if (not review_summary or review_summary.strip() == '') and google_place_id:
                fetched = get_place_review_summary(google_place_id)
                if fetched:
                    spot.review_summary = fetched
        except Exception as _:
            pass
        
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
        
        # 旧: 手動楽天アフィリエイトリンクは廃止

        # SNSリンクの更新
        _update_social_links(spot.id, request.form)

        # その他のリンクの更新
        _update_other_links(spot.id, request.form)

        db.session.commit()
        flash('スポットを追加しました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    return render_template('spot_form.html', is_edit=False, custom_links=[])

@bp.route('/edit-spot/<int:spot_id>', methods=['GET', 'POST'])
@login_required
def edit_spot(spot_id):
    """スポット編集ページ"""
    # アフィリエイトリンクを積極的に読み込む
    spot = Spot.query.options(joinedload(Spot.affiliate_links)).filter_by(id=spot_id, user_id=current_user.id).first_or_404()
    
    # 旧: 手動楽天リンクのデバッグ表示は廃止
    
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
        # レビューサマリーを更新（hidden優先、無ければサーバ側フォールバック）
        form_review_summary = request.form.get('review_summary', '')
        spot.review_summary = form_review_summary or spot.review_summary
        if (not spot.review_summary or spot.review_summary.strip() == '') and new_place_id:
            try:
                fetched = get_place_review_summary(new_place_id)
                if fetched:
                    spot.review_summary = fetched
            except Exception as _:
                pass
        
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
        
        # 旧: 手動楽天アフィリエイトリンクの更新/削除は廃止

        # SNSリンクの更新
        _update_social_links(spot.id, request.form)
        
        # その他のリンクの更新
        _update_other_links(spot.id, request.form)
        
        db.session.commit()
        flash('スポット情報を更新しました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    # ユーザーがアップロードした写真のみを取得（Google写真は除外）
    photos = Photo.query.filter_by(spot_id=spot_id, is_google_photo=False).all()

    # カスタムプラットフォームのアフィリエイトリンクを辞書形式で取得
    custom_links = [link.to_dict() for link in spot.affiliate_links if link.platform == 'custom']

    return render_template('spot_form.html', spot=spot, photos=photos, is_edit=True, custom_links=custom_links)

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