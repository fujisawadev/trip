from flask import Blueprint, render_template, abort, jsonify, redirect, Response, url_for, request
from app.models import User, Spot, Photo, SocialAccount, SocialPost
from app import db
from sqlalchemy.orm import joinedload
import requests
import os
import json
from flask_login import current_user

# 新しいサービスをインポート
from app.services.google_photos import get_google_photos_by_place_id, get_redis_client
from app.services.agoda import build_deeplink as build_agoda_deeplink
from app.services.agoda import fetch_price as fetch_agoda_price_by_hotel
from app.services.dataforseo import fetch_hotel_offers as dfs_fetch_hotel_offers
from app.services.dataforseo import normalize_offers_from_hotel_info as dfs_normalize
from app.services.affiliates import wrap_offers
from app.services.rakuten_travel import build_offer_from_hotel_no as rakuten_build_offer
from app.models.spot_provider_id import SpotProviderId

public_bp = Blueprint('public', __name__)

# Google Maps API Keyを環境変数から取得
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')

@public_bp.route('/test_photo_cdn/<path:photo_reference>')
def test_photo_cdn(photo_reference):
    """Google Photo ReferenceからCDN URLを取得するテスト"""
    if not photo_reference or photo_reference == 'null' or photo_reference == 'None':
        return jsonify({'error': '無効な写真参照'}), 400
    
    try:
        # skipHttpRedirect=trueを指定してJSONレスポンスを取得
        photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}&skipHttpRedirect=true"
        
        response = requests.get(photo_url)
        result = {
            'status_code': response.status_code,
            'content_type': response.headers.get('Content-Type'),
        }
        
        if response.status_code == 200:
            try:
                # JSONレスポンスを解析
                data = response.json()
                result['json_response'] = data
                
                # photoUriフィールドがあるか確認
                if 'photoUri' in data:
                    cdn_url = data['photoUri']
                    result['cdn_url'] = cdn_url
                    
                    # CDN URLにアクセスできるか確認
                    cdn_response = requests.head(cdn_url)
                    result['cdn_access'] = {
                        'status_code': cdn_response.status_code,
                        'content_type': cdn_response.headers.get('Content-Type')
                    }
                    
                    # HTMLテスト用のリンクを追加
                    result['html_test'] = f"""
                    <h2>CDN URL画像テスト</h2>
                    <img src="{cdn_url}" alt="Test Image" style="max-width: 400px;">
                    """
            except ValueError:
                # JSONではない場合
                result['error'] = 'JSONではないレスポンス'
                result['response_preview'] = response.text[:200]  # 最初の200文字
        else:
            result['error'] = response.text
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@public_bp.route('/u/<int:user_id>')
def profile(user_id):
    """公開プロフィールページを表示する（ユーザー名ベースのURLにリダイレクト）"""
    user = User.query.get_or_404(user_id)
    # ユーザー名ベースのURLにリダイレクト
    return redirect(url_for('public.username_profile', username=user.username))

# 新しいユーザー名ベースのルートを追加
@public_bp.route('/<username>')
def username_profile(username):
    """ユーザー名ベースの公開プロフィールページを表示する"""
    user = User.query.filter_by(username=username).first_or_404()
    
    # ユーザーが作成したスポットを取得（更新日時の新しい順）
    spots = Spot.query.filter_by(user_id=user.id, is_active=True).order_by(Spot.updated_at.desc()).all()
    
    # スポットをJSONシリアライズ可能な形式に変換
    spots_data = []
    categories = set()
    locations = set()
    prices = set()
    for spot in spots:
        d = spot.to_dict()
        # external_id（provider_ids）があるスポットのみ価格取得対象にする
        providers = [p.provider for p in getattr(spot, 'provider_ids', [])]
        d['has_offers'] = any(p in ['dataforseo', 'rakuten', 'agoda'] for p in providers)
        spots_data.append(d)
        if d.get('category'):
            categories.add(d['category'])
        loc = d.get('summary_location') or d.get('location')
        if loc:
            locations.add(loc)
        pr = d.get('price_range')
        if pr:
            prices.add(pr)

    # ソーシャルアカウント情報を取得
    social_accounts = SocialAccount.query.filter_by(user_id=user.id).first()
    
    return render_template('public/profile.html', 
                          user=user, 
                          spots=spots_data,
                          filter_categories=sorted(categories),
                          filter_locations=sorted(locations),
                          filter_prices=sorted(prices),
                          social_accounts=social_accounts,
                          config={'GOOGLE_MAPS_API_KEY': GOOGLE_MAPS_API_KEY})

@public_bp.route('/test_koshien_photo')
def test_koshien_photo():
    """甲子園（ID:5）のスポット情報を取得し、CDN URLを取得するためのテストエンドポイント"""
    from app.models import Spot, Photo
    import requests
    import os
    import json
    
    # 甲子園のスポット情報を取得（ID:5）
    spot = Spot.query.get(5)
    if not spot:
        return jsonify({"error": "Spot with ID 5 not found"}), 404
    
    # スポット情報を収集
    spot_info = {
        "spot_id": spot.id,
        "name": spot.name,
        "google_place_id": spot.google_place_id
    }
    
    # 関連する写真を取得
    photos = Photo.query.filter_by(spot_id=spot.id).all()
    photo_info = []
    for photo in photos:
        photo_info.append({
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "is_google_photo": photo.is_google_photo
        })
    
    spot_info["photos"] = photo_info
    
    # Google Photo Referenceが有効な場合、CDN URLを取得
    cdn_url = None
    cdn_accessible = False
    
    # Google Photo Reference機能は削除されたため、この機能は無効化
    spot_info["cdn_url"] = cdn_url
    spot_info["cdn_accessible"] = cdn_accessible
    
    # HTMLレスポンスを返す（テスト用）
    html_response = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>甲子園 Photo Test</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            pre {{ background: #f5f5f5; padding: 10px; overflow: auto; }}
            img {{ max-width: 100%; height: auto; margin: 10px 0; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>甲子園 Photo Test</h1>
            
            <h2>スポット情報</h2>
            <pre>{json.dumps(spot_info, indent=2, ensure_ascii=False)}</pre>
            
            <h2>Google Photo Reference</h2>
            <p>機能が削除されました</p>
            
            <h2>CDN URL</h2>
            <p>機能が削除されました</p>
            
            <h2>画像テスト</h2>
            <div>
                <h3>1. プロキシエンドポイント経由</h3>
                <img src="{url_for('static', filename='images/default_profile.png')}" alt="デフォルト画像">
                
                <h3>2. CDN URL直接アクセス（取得できた場合）</h3>
                <p>機能が削除されました</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_response

@public_bp.route('/photo_proxy/<path:photo_reference>')
def photo_proxy(photo_reference):
    """Google Photo Referenceを使用して画像を取得するプロキシエンドポイント"""
    import requests
    
    # photo_referenceが無効な場合は404エラーを返す（デフォルト画像へのリダイレクトを削除）
    if not photo_reference or photo_reference == 'null' or photo_reference == 'None':
        return jsonify({'error': '無効な写真参照'}), 404
    
    # まずCDN URLを取得
    try:
        cdn_url_response = requests.get(
            f"https://places.googleapis.com/v1/{photo_reference}/media?skipHttpRedirect=true&maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}",
            timeout=5
        )
        
        if cdn_url_response.status_code == 200:
            try:
                data = cdn_url_response.json()
                if 'photoUri' in data:
                    # CDN URLが取得できた場合、そのURLにリダイレクト
                    return redirect(data['photoUri'])
            except:
                # JSONデコードエラーなど、何らかの問題が発生した場合は直接画像を取得
                pass
    except:
        # リクエストエラーの場合は直接画像を取得
        pass
    
    # CDN URLが取得できなかった場合、直接画像を取得
    try:
        image_response = requests.get(
            f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}",
            timeout=5
        )
        
        if image_response.status_code == 200:
            # 画像データを返す
            return Response(
                image_response.content,
                content_type=image_response.headers.get('Content-Type', 'image/jpeg'),
                status=200
            )
    except:
        # 画像取得に失敗した場合
        pass
    
    # すべての方法が失敗した場合、404エラーを返す（デフォルト画像へのリダイレクトを削除）
    return jsonify({'error': '画像の取得に失敗しました'}), 404 

@public_bp.route('/<displayname>/map')
def displayname_map(displayname):
    """旧 new_map.html は廃止済み。プロフィールにリダイレクト。"""
    user = User.query.filter((User.display_name == displayname) | (User.username == displayname)).first_or_404()
    return redirect(url_for('public.username_profile', username=user.username))

@public_bp.route('/api/spots/<int:spot_id>')
def spot_api(spot_id):
    """スポット詳細をJSON形式で返すAPIエンドポイント"""
    try:
        # スポットとそれに関連する写真を一度に取得
        spot = Spot.query.options(joinedload(Spot.user)).get_or_404(spot_id)
        
        # 非公開のスポットの場合は404を返す
        if not spot.is_active:
            return jsonify({'error': 'スポットが見つかりません'}), 404
        
        # スポットに関連する写真を取得
        photos = Photo.query.filter_by(spot_id=spot_id).all()
        
        # JSONレスポンス用のデータを構築
        spot_data = {
            'id': spot.id,
            'name': spot.name,
            'description': spot.description,
            'location': spot.location,
            'category': spot.category,
            'latitude': spot.latitude,
            'longitude': spot.longitude,
            'google_place_id': spot.google_place_id,
            'created_at': spot.created_at.strftime('%Y-%m-%d'),
            'user': {
                'id': spot.user.id,
                'username': spot.user.username
            },
            'photos': []
        }
        
        # 写真データを追加
        for photo in photos:
            spot_data['photos'].append({
                'id': photo.id,
                'photo_url': photo.photo_url,
                'is_google_photo': photo.is_google_photo
            })
        
        # アフィリエイトリンクやSNS投稿などのダミーデータを追加（実際のデータがあれば置き換える）
        spot_data['affiliate_links'] = []
        spot_data['social_posts'] = []
        
        print(f"API Response for spot {spot_id}: {spot_data}")
        return jsonify(spot_data)
    except Exception as e:
        print(f"API Error for spot {spot_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500 

@public_bp.route('/terms')
def terms():
    """利用規約ページを表示する"""
    return render_template('public/terms.html')

@public_bp.route('/privacy-policy')
def privacy_policy():
    """プライバシーポリシーページを表示する"""
    return render_template('public/privacy_policy.html')

@public_bp.route('/commerce-law')
def commerce_law():
    """特定商取引法に基づく表記ページを表示する"""
    return render_template('public/commerce_law.html')

@public_bp.route('/<displayname>/<int:spot_id>')
def user_spot_detail(displayname, spot_id):
    """ユーザーの公開スポット詳細ページを表示"""
    # ユーザーとスポットを取得（存在しない場合は404）
    user = User.query.filter((User.username == displayname) | (User.display_name == displayname)).first_or_404()
    spot = Spot.query.filter_by(id=spot_id, user_id=user.id, is_active=True).first_or_404()

    # ユーザーがアップロードした写真とGoogle Photosを結合
    # 1. ユーザーがアップロードした写真を取得
    user_photos = Photo.query.filter_by(spot_id=spot.id, is_google_photo=False).order_by(Photo.is_primary.desc(), Photo.created_at.asc()).all()
    user_photo_urls = [p.photo_url for p in user_photos]

    # 2. Google PhotosをPlace ID経由で取得
    google_photo_urls = []
    if spot.google_place_id:
        google_photo_urls = get_google_photos_by_place_id(spot.google_place_id, max_photos=10)

    # 3. 写真を結合（ユーザー写真が先頭）
    all_photos = user_photo_urls + google_photo_urls
    
    # 関連するSNS投稿を取得し、プラットフォームごとのリンクを整理
    social_posts = SocialPost.query.filter_by(spot_id=spot.id).all()
    platforms = ['instagram', 'tiktok', 'twitter', 'youtube']
    social_links = {platform: None for platform in platforms}
    for post in social_posts:
        if post.platform in social_links:
            social_links[post.platform] = post.post_url

    # 価格比較ブロックの表示可否（DataForSEO or 楽天 or AgodaのIDがあるときに表示）
    has_offers = any((p.provider in ['dataforseo', 'rakuten', 'agoda']) for p in getattr(spot, 'provider_ids', []))
    
    return render_template('public/spot_detail.html', 
                          user=user, 
                          spot=spot, 
                          photos=all_photos,
                          social_links=social_links,
                          has_offers=has_offers)


@public_bp.route('/public/api/spots/<int:spot_id>/hotel_offers')
def public_spot_hotel_offers(spot_id: int):
    """公開: スポットのホテル価格オファー取得API
    クエリ: checkIn=YYYY-MM-DD, checkOut=YYYY-MM-DD, adults=2
    デフォルト: 翌日チェックイン/1泊, 大人2名
    """
    spot = Spot.query.get_or_404(spot_id)
    if not spot.is_active:
        return jsonify({'error': 'スポットが見つかりません'}), 404

    # 日付デフォルト: 翌日〜翌々日
    from datetime import date, timedelta
    check_in = request.args.get('checkIn')
    check_out = request.args.get('checkOut')
    adults = int(request.args.get('adults', '2'))

    if not check_in or not check_out:
        d1 = date.today() + timedelta(days=1)
        d2 = d1 + timedelta(days=1)
        check_in = d1.strftime('%Y-%m-%d')
        check_out = d2.strftime('%Y-%m-%d')

    # まずRedisキャッシュを確認（10分TTL想定）
    redis_client = get_redis_client()

    def build_cache_key(spot_id: int, check_in: str, check_out: str, adults: int, children: int) -> str:
        return f"hotel_offers:v1:{spot_id}:{check_in}:{check_out}:{adults}:{children}"

    def compute_min_offer(offers_list):
        def price_value(o):
            try:
                return float(o['price']) if o.get('price') is not None else float('inf')
            except Exception:
                return float('inf')
        if not offers_list:
            return None
        # 最小価格の要素を選択
        min_idx = None
        min_val = float('inf')
        for idx, o in enumerate(offers_list):
            v = price_value(o)
            if v < min_val:
                min_val = v
                min_idx = idx
        if min_idx is None or min_val == float('inf'):
            return None
        # 返却用のdict（キャッシュ破壊を避けコピー）
        mo = dict(offers_list[min_idx])
        mo['is_min_price'] = True
        return mo

    children = int(request.args.get('children', '0'))
    cache_key = build_cache_key(spot.id, check_in, check_out, adults, children)

    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                try:
                    offers_cached = json.loads(cached)
                except Exception:
                    offers_cached = None
                if isinstance(offers_cached, list):
                    # キャッシュヒット: サマリー/フルに応じて返却
                    summary = (request.args.get('summary') or '').lower() in ['1', 'true', 'yes']
                    if summary:
                        return jsonify({'min_offer': compute_min_offer(offers_cached)})
                    else:
                        return jsonify({'offers': offers_cached, 'min_offer': compute_min_offer(offers_cached)})
        except Exception:
            # キャッシュ障害時はそのまま計算へフォールバック
            pass

    offers = []

    # DataForSEOがあれば最優先（メタサーチとして複数OTAの価格・リンクを取得）
    dfs_map = SpotProviderId.query.filter_by(spot_id=spot.id, provider='dataforseo').first()
    if dfs_map:
        dfs_result = dfs_fetch_hotel_offers(
            hotel_identifier=dfs_map.external_id,
            language_code=os.environ.get('DATAFORSEO_DEFAULT_LANGUAGE', 'ja'),
            location_name=os.environ.get('DATAFORSEO_DEFAULT_LOCATION', 'Japan'),
            check_in=check_in,
            check_out=check_out,
            currency=os.environ.get('AGODA_CURRENCY', 'JPY'),
            adults=adults,
        )
        offers.extend(dfs_normalize(dfs_result))

    # 楽天トラベルIDがあれば個別で追加
    rakuten_map = SpotProviderId.query.filter_by(spot_id=spot.id, provider='rakuten').first()
    if rakuten_map:
        rakuten_offer = rakuten_build_offer(rakuten_map.external_id, check_in, check_out, adults)
        if rakuten_offer:
            offers.append(rakuten_offer)

    if offers:
        # 価格が数値のものを優先し昇順ソート
        def price_value(o):
            try:
                return float(o['price']) if o.get('price') is not None else float('inf')
            except Exception:
                return float('inf')
        offers.sort(key=price_value)
        # アフィリエイト包み（有効時）
        try:
            offers = wrap_offers(offers)
        except Exception:
            pass
        # キャッシュ保存（10分）
        if redis_client:
            try:
                redis_client.setex(cache_key, 600, json.dumps(offers))
            except Exception:
                pass
        # 応答
        summary = (request.args.get('summary') or '').lower() in ['1', 'true', 'yes']
        min_offer = offers[0] if offers and price_value(offers[0]) != float('inf') else None
        if summary:
            return jsonify({'min_offer': min_offer})
        return jsonify({'offers': offers, 'min_offer': min_offer})

    # Agodaフォールバック: DataForSEOマッピングが無い場合のみ
    has_agoda_mapping = SpotProviderId.query.filter_by(spot_id=spot.id, provider='agoda').first() is not None
    is_agoda = has_agoda_mapping

    sub_id = f"spot_{spot.id}"

    if is_agoda:
        # Agoda: まずはMVPとしてdeeplinkのみ（価格なし）。hotel_provider_idがAgodaのhotelIdなら使用。
        cid = os.environ.get('AGODA_PARTNER_ID')
        campaign_id = os.environ.get('AGODA_CAMPAIGN_ID')
        agoda_locale = os.environ.get('AGODA_LOCALE', 'ja-jp')
        agoda_currency = os.environ.get('AGODA_CURRENCY', 'JPY')
        # provider_id優先: SpotProviderId
        agoda_map = SpotProviderId.query.filter_by(spot_id=spot.id, provider='agoda').first()
        agoda_hotel_id = None
        if agoda_map:
            agoda_hotel_id = agoda_map.external_id

        children = int(request.args.get('children', '0'))
        deeplink = build_agoda_deeplink(
            agoda_hotel_id=agoda_hotel_id,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
            cid=cid,
            campaign_id=campaign_id,
            locale=agoda_locale,
            currency=agoda_currency,
            sub_id=sub_id,
        )
        # 価格取得（利用可能な場合のみ）
        price_info = None
        if agoda_hotel_id:
            price_info = fetch_agoda_price_by_hotel(
                hotel_id=agoda_hotel_id,
                check_in=check_in,
                check_out=check_out,
                adults=adults,
                locale=agoda_locale,
                currency=agoda_currency,
                sub_id=sub_id,
            )
        offer = {
            'provider': 'Agoda',
            'price': price_info.get('price') if price_info else None,
            'currency': price_info.get('currency') if price_info else agoda_currency,
            'deeplink': price_info.get('deeplink') if price_info and price_info.get('deeplink') else deeplink,
            'is_min_price': False,
        }
        # アフィリエイト包み（有効時）
        try:
            wrapped_single = wrap_offers([offer])
            if isinstance(wrapped_single, list) and wrapped_single:
                offer = wrapped_single[0]
        except Exception:
            pass
        # キャッシュ保存（10分）
        if redis_client:
            try:
                redis_client.setex(cache_key, 600, json.dumps([offer]))
            except Exception:
                pass
        summary = (request.args.get('summary') or '').lower() in ['1', 'true', 'yes']
        if summary:
            return jsonify({'min_offer': offer})
        return jsonify({'offers': [offer], 'min_offer': offer})
    else:
        # Hotellook分岐は廃止
        # キャッシュ保存（空でも短期キャッシュしてスパイク抑止）
        if redis_client:
            try:
                redis_client.setex(cache_key, 600, json.dumps([]))
            except Exception:
                pass
        summary = (request.args.get('summary') or '').lower() in ['1', 'true', 'yes']
        if summary:
            return jsonify({'min_offer': None})
        return jsonify({'offers': [], 'min_offer': None})