from flask import Blueprint, jsonify, current_app
from flask_login import current_user, login_required
from app import db
from app.models import StripeAccount, Withdrawal, PayoutLedger, LedgerEntry
from datetime import datetime, timedelta, timezone
import uuid

# 先にブループリントを定義（以降のデコレータ参照のため）
api_bp = Blueprint('api_routes', __name__, url_prefix='/api')

@api_bp.route('/me/withdrawals', methods=['POST'])
@login_required
def request_withdrawal_full_amount():
    """おさいふの出金可能額を全額で申請。72時間クールダウンを設定。"""
    user_id = current_user.id

    # KYC/受取設定チェック
    acct = StripeAccount.query.filter_by(user_id=user_id).first()
    if not (acct and acct.payouts_enabled and acct.requirements_json is not None):
        return jsonify({'error': 'payouts_not_enabled'}), 409

    # 出金可能額（前月まで未払い − on_hold）
    JST = timezone(timedelta(hours=9))
    today_jst = datetime.now(JST).date()
    this_month = _month_start(today_jst)

    unpaid = db.session.query(db.func.coalesce(db.func.sum(PayoutLedger.unpaid_balance), 0)) \
        .filter(PayoutLedger.user_id == user_id) \
        .filter(PayoutLedger.month < this_month) \
        .scalar() or 0

    hold_statuses = ['requested', 'pending_review', 'approved', 'transferring', 'payout_pending']
    on_hold = db.session.query(db.func.coalesce(db.func.sum(Withdrawal.amount), 0)) \
        .filter(Withdrawal.user_id == user_id) \
        .filter(Withdrawal.status.in_(hold_statuses)) \
        .scalar() or 0

    amount = float(unpaid) - float(on_hold)
    if amount < 0:
        amount = 0

    # 最小額チェック
    min_payout = current_app.config.get('MIN_PAYOUT_YEN', 1000)
    if amount < min_payout:
        return jsonify({'error': 'below_minimum', 'minimum': min_payout}), 400

    # 大型出金は審査キュー
    large_threshold = current_app.config.get('LARGE_PAYOUT_YEN', 100000)
    review_required = amount >= large_threshold

    # クールダウン72h
    cooldown_until = datetime.utcnow() + timedelta(hours=72)

    w = Withdrawal(
        user_id=user_id,
        amount=amount,
        status='pending_review' if review_required else 'requested',
        review_required=review_required,
        cooldown_until_at=cooldown_until,
        idempotency_key=f"payout:{user_id}:{datetime.utcnow().strftime('%Y%m%d')}:{uuid.uuid4().hex[:8]}"
    )
    db.session.add(w)

    # on_hold仕訳
    db.session.add(LedgerEntry(
        user_id=user_id,
        entry_type='withdrawal_hold',
        amount=amount,
        dr_cr='DR',
        ref_type='withdrawal',
        ref_id=None
    ))

    db.session.commit()
    return jsonify({'withdrawal_id': w.id, 'status': w.status, 'cooldown_until_at': cooldown_until.isoformat()}), 202


@api_bp.route('/me/withdrawals', methods=['GET'])
@login_required
def list_withdrawals():
    user_id = current_user.id
    items = (Withdrawal.query
             .filter_by(user_id=user_id)
             .order_by(Withdrawal.requested_at.desc())
             .limit(50)
             .all())
    resp = []
    for it in items:
        resp.append({
            'id': it.id,
            'amount': float(it.amount),
            'status': it.status,
            'requested_at': it.requested_at.isoformat() if it.requested_at else None,
            'cooldown_until_at': it.cooldown_until_at.isoformat() if it.cooldown_until_at else None,
        })
    return jsonify({'items': resp})
import os
import json
import requests
import logging
from flask import jsonify, request, abort, Blueprint, current_app, redirect
from app.models import Spot, Photo, SocialPost, ImportHistory, ImportProgress, User
from app.models import CreatorDaily, CreatorMonthly, PayoutLedger, PayoutTransaction
from app.models import StripeAccount, Withdrawal, Transfer as WithdrawalTransfer, Payout as WithdrawalPayout, LedgerEntry
import stripe
from sqlalchemy.orm import joinedload
from flask_login import current_user, login_required
from sqlalchemy import distinct
from app import db
import re
from datetime import datetime, timedelta
from app.utils.instagram_helpers import extract_cursor_from_url
from app.services.google_photos import get_google_photos_by_place_id
from app.utils.rakuten_api import search_hotel, generate_rakuten_affiliate_url, select_best_hotel_with_evaluation, simple_hotel_search_for_manual, search_hotel_with_fallback
from rq import Queue
from redis import Redis
from app.tasks import fetch_and_analyze_posts, save_spots_async
import uuid
 
 

# Google Places API Key
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
if not GOOGLE_MAPS_API_KEY:
    raise EnvironmentError("GOOGLE_MAPS_API_KEY environment variable is not set")

# OpenAI API Key
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY environment variable is not set. AI features will not work.")

# Stripe setup
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    print("Warning: STRIPE_SECRET_KEY is not set. Payout features will not work.")


@api_bp.route('/me/payout-settings/link', methods=['POST'])
@login_required
def create_payout_onboarding_link():
    """Stripe Connect ExpressのHosted Onboardingリンクを発行（なければアカウント作成）。"""
    if not STRIPE_SECRET_KEY:
        return jsonify({ 'error': 'stripe_not_configured' }), 500

    user = current_user

    acct = StripeAccount.query.filter_by(user_id=user.id).first()
    if not acct:
        # アカウントを作成
        try:
            created = stripe.Account.create(type='express', country='JP')
        except Exception as e:
            return jsonify({ 'error': 'stripe_error', 'message': str(e) }), 502

        acct = StripeAccount(
            user_id=user.id,
            stripe_account_id=created['id'],
            status='created',
            payouts_enabled=bool(created.get('payouts_enabled')),
            charges_enabled=bool(created.get('charges_enabled')),
            requirements_json=created.get('requirements')
        )
        db.session.add(acct)
        db.session.commit()

    # リンクを生成
    base_url = current_app.config.get('APP_BASE_URL') or request.host_url.rstrip('/')
    try:
        link = stripe.AccountLink.create(
            account=acct.stripe_account_id,
            type='account_onboarding',
            refresh_url=f"{base_url}/settings/monetization",
            return_url=f"{base_url}/settings/monetization"
        )
        return jsonify({ 'url': link['url'] })
    except Exception as e:
        return jsonify({ 'error': 'stripe_error', 'message': str(e) }), 502


@api_bp.route('/me/payout-settings/status', methods=['GET'])
@login_required
def get_payout_status():
    """ユーザーの受取設定（KYC/要件）ステータスを返す。"""
    acct = StripeAccount.query.filter_by(user_id=current_user.id).first()
    if not acct:
        return jsonify({ 'has_account': False, 'payouts_enabled': False, 'charges_enabled': False, 'requirements': None })
    return jsonify({
        'has_account': True,
        'payouts_enabled': bool(acct.payouts_enabled),
        'charges_enabled': bool(acct.charges_enabled),
        'requirements': acct.requirements_json,
        'stripe_account_id': acct.stripe_account_id
    })

def handle_instagram_api_error(response_text, status_code=None):
    """Instagram APIエラーを分析してユーザーフレンドリーなメッセージに変換"""
    try:
        error_data = json.loads(response_text)
        error_info = error_data.get('error', {})
        error_code = error_info.get('code')
        error_type = error_info.get('type')
        error_message = error_info.get('message', '')
        
        print(f"Instagram APIエラー詳細: code={error_code}, type={error_type}, message={error_message}")
        
        if error_code == 190:  # OAuthException - アクセストークン無効
            return {
                'user_message': 'Instagram連携の有効期限が切れています。SNS設定から再度連携してください。',
                'action': 'reauth_required',
                'action_url': '/profile/sns-settings',
                'error_code': error_code
            }
        elif error_code == 100:  # Invalid parameter
            return {
                'user_message': 'Instagram連携に問題があります。しばらく待ってから再度お試しください。',
                'action': 'retry_later',
                'error_code': error_code
            }
        elif error_code == 4:  # Application request limit reached
            return {
                'user_message': 'Instagram APIの利用制限に達しました。しばらく時間をおいてから再度お試しください。',
                'action': 'retry_later',
                'error_code': error_code
            }
        elif error_code == 17:  # User request limit reached
            return {
                'user_message': 'Instagram APIの利用制限に達しました。1時間ほど時間をおいてから再度お試しください。',
                'action': 'retry_later',
                'error_code': error_code
            }
        elif 'session has been invalidated' in error_message.lower():
            return {
                'user_message': 'Instagram連携が無効になっています。SNS設定から再度連携してください。',
                'action': 'reauth_required',
                'action_url': '/profile/sns-settings',
                'error_code': error_code
            }
        elif 'password' in error_message.lower():
            return {
                'user_message': 'Instagramのパスワード変更により連携が無効になりました。SNS設定から再度連携してください。',
                'action': 'reauth_required',
                'action_url': '/profile/sns-settings',
                'error_code': error_code
            }
        else:
            return {
                'user_message': 'Instagram連携でエラーが発生しました。SNS設定から連携状態を確認してください。',
                'action': 'check_settings',
                'action_url': '/profile/sns-settings',
                'error_code': error_code,
                'original_message': error_message
            }
    except json.JSONDecodeError:
        return {
            'user_message': 'Instagram連携でエラーが発生しました。時間をおいて再度お試しください。',
            'action': 'retry_later',
            'original_message': response_text
        }
    except Exception as e:
        print(f"エラーハンドリング中にエラー: {e}")
        return {
            'user_message': 'Instagram連携でエラーが発生しました。時間をおいて再度お試しください。',
            'action': 'retry_later'
        }

@api_bp.route('/spots/<int:spot_id>', methods=['GET'])
def get_spot(spot_id):
    """スポット詳細情報を取得するAPI"""
    # スポットとそれに関連する写真、アフィリエイトリンク、SNS投稿を一度に取得
    spot = Spot.query.options(
        joinedload(Spot.photos),
        joinedload(Spot.social_posts),
        joinedload(Spot.user)
    ).get_or_404(spot_id)
    
    # 非公開のスポットの場合は404を返す
    if not spot.is_active:
        abort(404)
    
    # Google Maps URLを生成
    google_maps_url = spot.google_maps_url
    if not google_maps_url:
        if spot.google_place_id:
            google_maps_url = f"https://www.google.com/maps/search/?api=1&query={spot.name}&query_place_id={spot.google_place_id}"
        elif spot.latitude and spot.longitude:
            google_maps_url = f"https://www.google.com/maps/search/?api=1&query={spot.latitude},{spot.longitude}"
        else:
            google_maps_url = f"https://www.google.com/maps/search/?api=1&query={spot.name}"
    
    # スポットデータをJSON形式で返す
    spot_data = {
        'id': spot.id,
        'name': spot.name,
        'description': spot.description,
        'summary_location': spot.summary_location,
        'location': spot.location,
        'category': spot.category,
        'latitude': spot.latitude,
        'longitude': spot.longitude,
        'rating': spot.rating,
        'review_count': spot.review_count,
        'user_display_name': spot.user.display_name if spot.user else None,
        'google_maps_url': google_maps_url,
        'photos': [
            {
                'id': photo.id,
                'photo_url': photo.photo_url
            } for photo in spot.photos
        ],
        'custom_link': {
            'title': spot.custom_link_title,
            'url': spot.custom_link_url,
        } if (spot.custom_link_title or spot.custom_link_url) else None,
        'social_posts': [
            {
                'id': post.id,
                'platform': post.platform,
                'post_url': post.post_url,
                'thumbnail_url': post.thumbnail_url,
                'caption': post.caption
            } for post in spot.social_posts
        ] if hasattr(spot, 'social_posts') else []
    }
    
    return jsonify(spot_data)

@api_bp.route('/places/details', methods=['GET'])
def place_details():
    """Google Place Details APIを呼び出す"""
    place_id = request.args.get('place_id', '')
    if not place_id:
        return jsonify({'error': 'Place ID is required'}), 400
    
    # 新しいGoogle Places API v1を呼び出す
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
        'X-Goog-FieldMask': 'displayName,formattedAddress,location,types,photos,editorialSummary,reviewSummary',
        'X-Goog-LanguageCode': 'ja',  # 日本語を指定（ヘッダー）
        'User-Agent': 'my-map.link App (https://my-map.link)'
    }
    
    print(f"Calling Google Places API v1 Details with URL: {url}")
    print(f"Headers: {headers}")
    
    try:
        # GETリクエストを使用
        # ヘッダーだけでなく、クエリにも languageCode=ja を明示
        response = requests.get(url, headers=headers, params={'languageCode': 'ja'})
        print(f"Response status code: {response.status_code}")
        data = response.json()
        print(f"Google Places API response: {data}")
        
        if response.status_code != 200:
            error_message = data.get('error', {}).get('message', 'Unknown error')
            print(f"API Error: {error_message}")
            
            # APIエラーの場合はモックデータを返す（開発用）
            mock_details = {
                'ChIJCzp6MFqLGGARQLKnq1z1Ags': {
                    'name': '東京タワー',
                    'formatted_address': '〒105-0011 東京都港区芝公園４丁目２−８',
                    'latitude': 35.6585805,
                    'longitude': 139.7454329,
                    'types': ['tourist_attraction', 'point_of_interest', 'establishment'],
                    'place_id': 'ChIJCzp6MFqLGGARQLKnq1z1Ags',
                    'thumbnail_url': 'https://lh3.googleusercontent.com/places/ANJU3DuWC5aDo9rGKBZ9FwpQqiP8Y0T0W9yxCLGKPUXGPOQlQoJ_RBNjgTFTMXKApNk-FLgCJrKUG4yWBKlNpA9vqkYRZLZVEehZTHM=s1600-w400',
                    'photo_reference': 'photos/ChIJCzp6MFqLGGARQLKnq1z1Ags/photo1'
                },
                'ChIJL2P59YOLGGARuPGj8_tFxjo': {
                    'name': '東京スカイツリー',
                    'formatted_address': '〒131-0045 東京都墨田区押上１丁目１−２',
                    'latitude': 35.7100627,
                    'longitude': 139.8107004,
                    'types': ['tourist_attraction', 'point_of_interest', 'establishment'],
                    'place_id': 'ChIJL2P59YOLGGARuPGj8_tFxjo',
                    'thumbnail_url': 'https://lh3.googleusercontent.com/places/ANJU3DvMCYcDFi9L7qHEBgXgJzL-Ux9_2-j5mtCY_1-XiKpJgHDGY9Jya_5xcWQQrDw0j9i9UjGBhZYj1KbgEd_X_LLFYFVdQGjbvlI=s1600-w400',
                    'photo_reference': 'photos/ChIJL2P59YOLGGARuPGj8_tFxjo/photo1'
                }
            }
            
            if place_id in mock_details:
                print(f"Returning mock data for place_id: {place_id}")
                return jsonify(mock_details[place_id])
            
            return jsonify({'error': f'Failed to get place details: {error_message}'}), 400
        
        # 新しいAPIのレスポンス形式に合わせて変換
        place_details = {
            'name': data.get('displayName', {}).get('text', ''),
            'formatted_address': data.get('formattedAddress', ''),
            'latitude': data.get('location', {}).get('latitude', None),
            'longitude': data.get('location', {}).get('longitude', None),
            'types': data.get('types', []),
            'place_id': place_id
        }

        # レビュー要約（editorialSummary を優先、フォールバックで reviewSummary）
        try:
            editorial = data.get('editorialSummary')
            review_summary_text = None
            if isinstance(editorial, dict):
                txt = editorial.get('text')
                if isinstance(txt, str) and txt.strip():
                    review_summary_text = txt.strip()
            elif isinstance(editorial, str) and editorial.strip():
                review_summary_text = editorial.strip()

            if not review_summary_text:
                rs = data.get('reviewSummary')
                if isinstance(rs, dict):
                    # 代表的な形: { text: "..." } や { overview: { text: "..." } }
                    txt = rs.get('text')
                    if isinstance(txt, str) and txt.strip():
                        review_summary_text = txt.strip()
                    else:
                        overview = rs.get('overview') if isinstance(rs.get('overview'), dict) else None
                        if overview and isinstance(overview.get('text'), str) and overview.get('text').strip():
                            review_summary_text = overview.get('text').strip()
                elif isinstance(rs, str) and rs.strip():
                    review_summary_text = rs.strip()

            if review_summary_text:
                place_details['review_summary'] = review_summary_text
        except Exception:
            pass
        
        # 写真がある場合は最初の1枚のURLを取得
        if 'photos' in data and len(data['photos']) > 0:
            photo = data['photos'][0]
            photo_reference = photo.get('name', '')
            if photo_reference:
                # 新しいPhotos APIのエンドポイントを使用
                photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}"
                place_details['thumbnail_url'] = photo_url
                place_details['photo_reference'] = photo_reference  # 写真参照情報を追加
                print(f"Photo URL: {photo_url}")
        
        # 常にsearchTextエンドポイントを使用して日本語の情報を取得
        # X-Goog-LanguageCodeヘッダーでは日本語が取得できないため
        search_url = "https://places.googleapis.com/v1/places:searchText"
        search_headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
            'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.types,places.addressComponents'
        }
        search_data = {
            'textQuery': place_details['name'],  # 英語の名前で検索
            'languageCode': 'ja',
            'regionCode': 'jp'
        }
        
        print(f"Calling searchText API with URL: {search_url}")
        print(f"Search headers: {search_headers}")
        print(f"Search data: {search_data}")
        
        search_response = requests.post(search_url, headers=search_headers, json=search_data)
        if search_response.status_code == 200:
            search_data = search_response.json()
            print(f"Search API response: {search_data}")
            
            if 'places' in search_data and len(search_data['places']) > 0:
                place = search_data['places'][0]
                place_details['name'] = place.get('displayName', {}).get('text', place_details['name'])
                place_details['formatted_address'] = place.get('formattedAddress', place_details['formatted_address'])
                
                # types情報も更新
                if 'types' in place and place['types']:
                    place_details['types'] = place['types']
                
                # サマリーロケーションを生成
                if 'addressComponents' in place:
                    country = None
                    prefecture = None
                    locality = None
                    
                    for component in place['addressComponents']:
                        types = component.get('types', [])
                        if 'country' in types:
                            country = component.get('longText')
                        elif 'administrative_area_level_1' in types:
                            prefecture = component.get('longText')
                        elif 'locality' in types:
                            locality = component.get('longText')
                    
                    # サマリーロケーションを構築
                    summary_parts = []
                    if country and country != "日本":
                        summary_parts.append(country)
                    if prefecture:
                        summary_parts.append(prefecture)
                    if locality:
                        summary_parts.append(locality)
                    
                    if summary_parts:
                        place_details['summary_location'] = '、'.join(summary_parts)
                        print(f"日本語のsummary_locationを設定: {place_details['summary_location']}")
        
        # summary_locationが設定されていない、または日本語でない場合は、Nominatim APIを使用して取得を試みる
        if 'summary_location' not in place_details or not is_japanese(place_details.get('summary_location', '')):
            try:
                print(f"Nominatim APIを使用して日本語の地名情報を取得します")
                if place_details.get('latitude') and place_details.get('longitude'):
                    nominatim_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={place_details['latitude']}&lon={place_details['longitude']}&accept-language=ja"
                    nominatim_headers = {
                        'User-Agent': 'my-map.link App (https://my-map.link)'
                    }
                    
                    nominatim_response = requests.get(nominatim_url, headers=nominatim_headers)
                    if nominatim_response.status_code == 200:
                        nominatim_data = nominatim_response.json()
                        
                        if 'address' in nominatim_data:
                            address = nominatim_data['address']
                            summary_parts = []
                            
                            if 'country' in address and address['country'] != "日本":
                                summary_parts.append(address['country'])
                            if 'state' in address:
                                summary_parts.append(address['state'])
                            if 'city' in address or 'town' in address or 'village' in address:
                                summary_parts.append(address.get('city') or address.get('town') or address.get('village'))
                            
                            if summary_parts:
                                place_details['summary_location'] = '、'.join(summary_parts)
                                print(f"Nominatim APIから日本語のsummary_locationを設定: {place_details['summary_location']}")
            except Exception as e:
                print(f"Nominatim API呼び出しエラー: {str(e)}")
        
        return jsonify(place_details)
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        
        # エラーの場合はモックデータを返す（開発用）
        mock_details = {
            'ChIJCzp6MFqLGGARQLKnq1z1Ags': {
                'name': '東京タワー',
                'formatted_address': '〒105-0011 東京都港区芝公園４丁目２−８',
                'latitude': 35.6585805,
                'longitude': 139.7454329,
                'types': ['tourist_attraction', 'point_of_interest', 'establishment'],
                'place_id': 'ChIJCzp6MFqLGGARQLKnq1z1Ags',
                'thumbnail_url': 'https://lh3.googleusercontent.com/places/ANJU3DuWC5aDo9rGKBZ9FwpQqiP8Y0T0W9yxCLGKPUXGPOQlQoJ_RBNjgTFTMXKApNk-FLgCJrKUG4yWBKlNpA9vqkYRZLZVEehZTHM=s1600-w400',
                'photo_reference': 'photos/ChIJCzp6MFqLGGARQLKnq1z1Ags/photo1'
            },
            'ChIJL2P59YOLGGARuPGj8_tFxjo': {
                'name': '東京スカイツリー',
                'formatted_address': '〒131-0045 東京都墨田区押上１丁目１−２',
                'latitude': 35.7100627,
                'longitude': 139.8107004,
                'types': ['tourist_attraction', 'point_of_interest', 'establishment'],
                'place_id': 'ChIJL2P59YOLGGARuPGj8_tFxjo',
                'thumbnail_url': 'https://lh3.googleusercontent.com/places/ANJU3DvMCYcDFi9L7qHEBgXgJzL-Ux9_2-j5mtCY_1-XiKpJgHDGY9Jya_5xcWQQrDw0j9i9UjGBhZYj1KbgEd_X_LLFYFVdQGjbvlI=s1600-w400',
                'photo_reference': 'photos/ChIJL2P59YOLGGARuPGj8_tFxjo/photo1'
            }
        }
        
        if place_id in mock_details:
            print(f"Returning mock data for place_id: {place_id} due to exception: {str(e)}")
            return jsonify(mock_details[place_id])
        
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@api_bp.route('/places/autocomplete', methods=['GET', 'POST'])
def places_autocomplete():
    """Googleプレイス検索機能のオートコンプリートAPI
    queryパラメータを受け取り、その文字列に基づく場所の候補リストを返す
    """
    # GETとPOSTの両方に対応
    if request.method == 'POST':
        data = request.get_json()
        query = data.get('query', '')
    else:
        query = request.args.get('query', '')
    
    if not query or len(query) < 3:
        return jsonify([])
    
    # 新しいGoogle Places API v1を呼び出す
    url = "https://places.googleapis.com/v1/places:autocomplete"
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
        'X-Goog-FieldMask': 'suggestions.placePrediction.structuredFormat.mainText.text,suggestions.placePrediction.structuredFormat.secondaryText.text,suggestions.placePrediction.placeId',
        'X-Goog-LanguageCode': 'ja',  # 日本語を指定
        'User-Agent': 'my-map.link App (https://my-map.link)'
    }
    
    data = {
        'input': query,
        'languageCode': 'ja',  # 日本語を指定
        'regionCode': 'jp'     # 日本の地域コードを指定
    }
    
    print(f"Calling Google Places API v1 with URL: {url}")
    print(f"Headers: {headers}")
    print(f"Request data: {data}")
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Response status code: {response.status_code}")
        response_data = response.json()
        print(f"Google Places API response: {response_data}")
        
        if 'suggestions' not in response_data:
            print(f"API Error: No suggestions in response")
            # APIエラーの場合はモックデータを返す（開発用）
            if 'tokyo' in query.lower():
                mock_results = [
                    {
                        'place_id': 'ChIJCzp6MFqLGGARQLKnq1z1Ags',
                        'description': '東京タワー',
                        'secondary_text': 'Japan, Tokyo, Minato City, Shibakoen, 4 Chome−2−8',
                        'types': ['tourist_attraction', 'point_of_interest', 'establishment']
                    },
                    {
                        'place_id': 'ChIJL2P59YOLGGARuPGj8_tFxjo',
                        'description': '東京スカイツリー',
                        'secondary_text': 'Japan, Tokyo, Sumida City, Oshiage, 1 Chome−1−2',
                        'types': ['tourist_attraction', 'point_of_interest', 'establishment']
                    }
                ]
                return jsonify(mock_results)
            return jsonify([])
        
        results = []
        for suggestion in response_data.get('suggestions', []):
            prediction = suggestion.get('placePrediction', {})
            structured_format = prediction.get('structuredFormat', {})
            
            main_text = structured_format.get('mainText', {}).get('text', '')
            secondary_text = structured_format.get('secondaryText', {}).get('text', '')
            place_id = prediction.get('placeId', '')
            
            results.append({
                'place_id': place_id,
                'description': main_text,
                'secondary_text': secondary_text,
                'types': []  # 新APIではtypesが直接返されないため空配列を設定
            })
        
        return jsonify(results)
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        # エラーの場合はモックデータを返す（開発用）
        if 'tokyo' in query.lower():
            mock_results = [
                {
                    'place_id': 'ChIJCzp6MFqLGGARQLKnq1z1Ags',
                    'description': '東京タワー',
                    'secondary_text': 'Japan, Tokyo, Minato City, Shibakoen, 4 Chome−2−8',
                    'types': ['tourist_attraction', 'point_of_interest', 'establishment']
                },
                {
                    'place_id': 'ChIJL2P59YOLGGARuPGj8_tFxjo',
                    'description': '東京スカイツリー',
                    'secondary_text': 'Japan, Tokyo, Sumida City, Oshiage, 1 Chome−1−2',
                    'types': ['tourist_attraction', 'point_of_interest', 'establishment']
                }
            ]
            return jsonify(mock_results)
        return jsonify([])

@api_bp.route('/places/photo', methods=['GET'])
def place_photo():
    """Google Place Photos APIを呼び出す
    
    place_idを受け取り、写真のURLを返す。
    写真が見つからない場合は空のJSONを返す。
    """
    place_id = request.args.get('place_id', '')
    if not place_id:
        return jsonify({'error': 'Place ID is required'}), 400
    
    print(f"place_photo API called with place_id: {place_id}")
    
    # 開発用のモックデータ
    mock_photos = {
        'ChIJCzp6MFqLGGARQLKnq1z1Ags': 'https://lh3.googleusercontent.com/places/ANJU3DuWC5aDo9rGKBZ9FwpQqiP8Y0T0W9yxCLGKPUXGPOQlQoJ_RBNjgTFTMXKApNk-FLgCJrKUG4yWBKlNpA9vqkYRZLZVEehZTHM=s1600-w400',
        'ChIJL2P59YOLGGARuPGj8_tFxjo': 'https://lh3.googleusercontent.com/places/ANJU3DvMCYcDFi9L7qHEBgXgJzL-Ux9_2-j5mtCY_1-XiKpJgHDGY9Jya_5xcWQQrDw0j9i9UjGBhZYj1KbgEd_X_LLFYFVdQGjbvlI=s1600-w400',
        'ChIJq6YCCvBcGGARbAcQb4LatO4': 'https://lh3.googleusercontent.com/places/ANJU3DuCQYj_6h9W_5wGLEWEwezf5WgXkQpn_Jj2HgQKQsujAcXUXWQgO5m1SkQJ-jFKGBxQ7vTmC9W-NUe_3zRF-BpgXHh-ZQwQnQs=s1600-w400',
        'ChIJ89TugkeMGGARDmSeJIiyWFA': 'https://lh3.googleusercontent.com/places/ANJU3DtYANBHlSXlY_zxwVvJ_Yx0qRWU8xBJ9m_BdlVJPEU-2Gf2-XF_CWpV_LKu1QQKQnlOTIJYvvYi-kFQxGEZGX-_nqLHJZQXnXo=s1600-w400'
    }
    
    # モックデータがある場合は返す（開発用）
    if place_id in mock_photos:
        print(f"Returning mock photo for place_id: {place_id}")
        print(f"Mock photo URL: {mock_photos[place_id]}")
        return jsonify({'photo_url': mock_photos[place_id]})
    
    # 新しいGoogle Places API v1を呼び出す
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
        'X-Goog-FieldMask': 'photos.0.name',  # 最初の写真のみ取得
        'User-Agent': 'my-map.link App (https://my-map.link)'
    }
    
    print(f"Calling Google Places API with URL: {url}")
    print(f"Headers: {headers}")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"API Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"API Error response: {response.text}")
            return jsonify({})
        
        data = response.json()
        print(f"API Response data: {data}")
        
        # 写真がある場合は最初の1枚のURLを取得
        if 'photos' in data and len(data['photos']) > 0:
            photo = data['photos'][0]
            photo_reference = photo.get('name', '')
            if photo_reference:
                # 新しいPhotos APIのエンドポイントを使用
                photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}"
                print(f"Generated photo URL: {photo_url}")
                return jsonify({'photo_url': photo_url})
            else:
                print("No photo reference found in API response")
        else:
            print("No photos found in API response")
        
        # 写真が見つからない場合は空のJSONを返す
        return jsonify({})
    except Exception as e:
        print(f"Exception in place_photo: {str(e)}")
        return jsonify({}), 500

@api_bp.route('/google-photo/<int:photo_id>', methods=['GET'])
def get_google_photo(photo_id):
    """Google Places APIの写真参照情報を使用して写真URLを取得するAPI"""
    # 写真情報を取得
    photo = Photo.query.get_or_404(photo_id)
    
    # Google写真参照情報機能は削除されました
    if not photo.is_google_photo:
        return jsonify({'error': 'Google photo reference feature has been removed'}), 404
    
    return jsonify({
        'photo_id': photo.id,
        'photo_url': photo.photo_url,
        'is_google_photo': photo.is_google_photo,
        'message': 'Google photo reference feature has been removed'
    })

@api_bp.route('/spot/<int:spot_id>/photos', methods=['GET'])
def get_spot_photos(spot_id):
    """スポットに関連する写真情報を取得するAPI"""
    # スポットが存在するか確認
    spot = Spot.query.get_or_404(spot_id)
    
    # 非公開のスポットの場合は404を返す
    if not spot.is_active:
        abort(404)
    
    # スポットに関連する写真を取得
    photos = Photo.query.filter_by(spot_id=spot_id).all()
    
    # 写真情報をJSON形式で返す
    photos_data = []
    for photo in photos:
        photo_data = {
            'id': photo.id,
            'is_google_photo': photo.is_google_photo,
            'photo_url': photo.photo_url
        }
        
        photos_data.append(photo_data)
    
    return jsonify({
        'spot_id': spot_id,
        'photos': photos_data
    })

@api_bp.route('/user/categories', methods=['GET'])
def get_user_categories():
    """ユーザーが過去に登録したカテゴリの一覧を取得するAPI"""
    try:
        if not current_user.is_authenticated:
            return jsonify([])
        
        # ユーザーの過去のカテゴリを重複なしで取得
        categories = db.session.query(distinct(Spot.category))\
            .filter(Spot.user_id == current_user.id)\
            .filter(Spot.category.isnot(None))\
            .filter(Spot.category != '')\
            .order_by(Spot.category)\
            .all()
        
        # タプルのリストを文字列のリストに変換
        categories = [category[0] for category in categories]
        
        return jsonify(categories)
    except Exception as e:
        print(f"Error in get_user_categories: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/spots/<int:spot_id>/google-maps-url', methods=['GET'])
def get_google_maps_url(spot_id):
    """スポットのGoogle Maps URLを取得するAPI"""
    spot = Spot.query.get_or_404(spot_id)
    
    # 非公開のスポットの場合は404を返す
    if not spot.is_active:
        abort(404)
    
    # Google Maps URLを生成
    if spot.google_maps_url:
        url = spot.google_maps_url
    elif spot.google_place_id:
        url = f"https://www.google.com/maps/search/?api=1&query={spot.name}&query_place_id={spot.google_place_id}"
    elif spot.latitude and spot.longitude:
        url = f"https://www.google.com/maps/search/?api=1&query={spot.latitude},{spot.longitude}"
    else:
        url = f"https://www.google.com/maps/search/?api=1&query={spot.name}"
    
    return jsonify({'google_maps_url': url})


# ============================
# Wallet API
# ============================

def _month_start(d):
    return d.replace(day=1)

def _next_month_start(d):
    if d.month == 12:
        return d.replace(year=d.year+1, month=1, day=1)
    return d.replace(month=d.month+1, day=1)


@api_bp.route('/wallet/summary', methods=['GET'])
@login_required
def wallet_summary():
    user_id = current_user.id

    from datetime import datetime, timedelta, timezone
    JST = timezone(timedelta(hours=9))
    today_jst = datetime.now(JST).date()
    this_month = _month_start(today_jst)
    last_month = _month_start(this_month - timedelta(days=1))

    # withdrawable_balance: 前月までの未払い合計
    unpaid = db.session.query(db.func.coalesce(db.func.sum(PayoutLedger.unpaid_balance), 0)) \
        .filter(PayoutLedger.user_id == user_id) \
        .filter(PayoutLedger.month < this_month) \
        .scalar() or 0

    # on_hold: 申請中・処理中の拘束額（重複申請防止のため差し引く）
    hold_statuses = ['requested', 'pending_review', 'approved', 'transferring', 'payout_pending']
    on_hold = db.session.query(db.func.coalesce(db.func.sum(Withdrawal.amount), 0)) \
        .filter(Withdrawal.user_id == user_id) \
        .filter(Withdrawal.status.in_(hold_statuses)) \
        .scalar() or 0

    withdrawable = float(unpaid) - float(on_hold)
    if withdrawable < 0:
        withdrawable = 0

    # 受取可フラグ（KYC/口座完了判定）
    acct = StripeAccount.query.filter_by(user_id=user_id).first()
    payouts_enabled = bool(acct.payouts_enabled) if acct else False

    # this_month_estimated: 当月の Σ payout_day
    estimated = db.session.query(db.func.coalesce(db.func.sum(CreatorDaily.payout_day), 0)) \
        .filter(CreatorDaily.user_id == user_id) \
        .filter(CreatorDaily.day >= this_month) \
        .filter(CreatorDaily.day < _next_month_start(this_month)) \
        .scalar() or 0

    # next_payout_date: 翌月末（JST）
    from calendar import monthrange
    nm = _next_month_start(this_month)
    last_day = monthrange(nm.year, nm.month)[1]
    next_payout_date = nm.replace(day=last_day)

    return jsonify({
        'withdrawable_balance': round(float(withdrawable), 0),
        'this_month_estimated': round(float(estimated), 0),
        'minimum_payout_yen': int(current_app.config.get('MIN_PAYOUT_YEN', 1000)),
        'payouts_enabled': payouts_enabled,
        'on_hold': round(float(on_hold), 0),
        'next_payout_date': next_payout_date.isoformat(),
        'last_closed_month': this_month.isoformat()
    })


@api_bp.route('/wallet/current', methods=['GET'])
@login_required
def wallet_current():
    user_id = current_user.id
    from datetime import datetime, timedelta, timezone
    JST = timezone(timedelta(hours=9))
    today_jst = datetime.now(JST).date()
    this_month = _month_start(today_jst)

    q = db.session.query(
        db.func.coalesce(db.func.sum(CreatorDaily.pv), 0),
        db.func.coalesce(db.func.sum(CreatorDaily.clicks), 0),
        db.func.coalesce(db.func.sum(CreatorDaily.payout_day), 0),
        db.func.coalesce(db.func.avg(CreatorDaily.ctr), 0),
        db.func.coalesce(db.func.avg(CreatorDaily.ecmp), 0),
        db.func.percentile_cont(0.5).within_group(CreatorDaily.price_median)
    ).filter(
        CreatorDaily.user_id == user_id,
        CreatorDaily.day >= this_month,
        CreatorDaily.day < _next_month_start(this_month)
    ).first()

    pv, clicks, revenue, ctr, ecpm, price_median = q

    # cpc_dynamic は代表値として直近日の平均（なければ0）
    from sqlalchemy import desc
    last_daily = CreatorDaily.query.filter_by(user_id=user_id) \
        .order_by(desc(CreatorDaily.day)).first()
    cpc_dynamic = float(last_daily.cpc_dynamic) if last_daily and last_daily.cpc_dynamic is not None else 0.0

    return jsonify({
        'month': this_month.isoformat(),
        'pv': int(pv or 0),
        'clicks': int(clicks or 0),
        'estimated_revenue': round(float(revenue or 0), 0),
        'ctr': float(ctr or 0),
        'ecpm': round(float(ecpm or 0)),
        'price_median': float(price_median or 0) if price_median is not None else 0,
        'cpc_dynamic': cpc_dynamic
    })


@api_bp.route('/wallet/trends', methods=['GET'])
@login_required
def wallet_trends():
    user_id = current_user.id
    from datetime import datetime, timedelta, timezone
    JST = timezone(timedelta(hours=9))
    today_jst = datetime.now(JST).date()
    this_month = _month_start(today_jst)
    months_param = request.args.get('months', default=3, type=int)

    months = []
    pv_list, clicks_list, revenue_list = [], [], []

    # 過去n-1か月: creator_monthly、当月: creator_daily
    for i in range(months_param):
        m_start = _month_start(this_month - timedelta(days=1)) if i == months_param - 1 else _month_start(this_month - timedelta(days=30*(months_param-1-i)))
    
    # 正確に直近nヶ月を生成
    months_seq = []
    cur = _month_start(this_month - timedelta(days=1))  # 前月初
    for _ in range(months_param - 1):
        months_seq.append(cur)
        cur = _month_start(cur - timedelta(days=1))
    months_seq = list(reversed(months_seq)) + [this_month]

    for m in months_seq:
        if m == this_month:
            # 当月: daily 合算
            q = db.session.query(
                db.func.coalesce(db.func.sum(CreatorDaily.pv), 0),
                db.func.coalesce(db.func.sum(CreatorDaily.clicks), 0),
                db.func.coalesce(db.func.sum(CreatorDaily.payout_day), 0),
            ).filter(
                CreatorDaily.user_id == user_id,
                CreatorDaily.day >= this_month,
                CreatorDaily.day < _next_month_start(this_month)
            ).first()
            pv, clicks, revenue = q
        else:
            cm = CreatorMonthly.query.filter_by(user_id=user_id, month=m).first()
            pv = int(cm.pv) if cm else 0
            clicks = int(cm.clicks) if cm else 0
            revenue = float(cm.payout_month) if cm else 0
        months.append(m.isoformat())
        pv_list.append(int(pv or 0))
        clicks_list.append(int(clicks or 0))
        revenue_list.append(round(float(revenue or 0), 0))

    return jsonify({
        'months': months,
        'pv': pv_list,
        'clicks': clicks_list,
        'revenue': revenue_list
    })


@api_bp.route('/wallet/payouts', methods=['GET'])
@login_required
def wallet_payouts():
    user_id = current_user.id
    items = PayoutTransaction.query.filter_by(user_id=user_id).order_by(PayoutTransaction.paid_at.desc().nullslast()).all()
    resp = []
    for it in items:
        resp.append({
            'paid_at': it.paid_at.isoformat() if it.paid_at else None,
            'amount': float(it.amount),
            'month': None  # 将来: 紐づく締め月を保存する場合に設定
        })
    return jsonify({'items': resp})

@api_bp.route('/import/instagram/fetch', methods=['POST'])
def fetch_instagram_posts():
    """Instagramから投稿を取得するAPI"""
    print("=== Instagram投稿取得API開始 ===")
    if not current_user.is_authenticated:
        print("エラー: 認証されていないユーザー")
        return jsonify({'error': 'Authentication required'}), 401
    
    print(f"ユーザーID: {current_user.id}, ユーザー名: {current_user.username}")
    print(f"Instagram連携状態: token={current_user.instagram_token is not None}")
    
    if not current_user.instagram_token:
        print("エラー: Instagramアカウントが連携されていません")
        return jsonify({'error': 'Instagram account not connected'}), 400
    
    # リクエストからパラメータを取得
    data = request.get_json() or {}
    limit = data.get('limit', 50)  # デフォルトは50件
    after = data.get('after')  # ページネーションカーソル
    start_date = data.get('start_date')  # 開始日
    end_date = data.get('end_date')  # 終了日
    
    print(f"リクエストパラメータ: limit={limit}, after={after}, start_date={start_date}, end_date={end_date}")
    
    try:
        # Instagram Graph APIを呼び出す
        url = f"https://graph.instagram.com/v22.0/me/media"
        params = {
            "fields": "id,caption,media_type,media_url,permalink,timestamp,location",
            "access_token": current_user.instagram_token,
            "limit": limit
        }
        
        # ページネーションカーソルがある場合は追加
        if after:
            params["after"] = after
        
        print(f"Instagram Graph API呼び出し: URL={url}")
        print(f"パラメータ: fields={params['fields']}, limit={params['limit']}")
        
        response = requests.get(url, params=params)
        
        print(f"Instagram Graph APIレスポンス: ステータスコード={response.status_code}")
        
        if response.status_code != 200:
            print(f"Instagram Graph APIエラー: {response.text}")
            error_info = handle_instagram_api_error(response.text, response.status_code)
            return jsonify({
                'error': error_info['user_message'],
                'action': error_info.get('action'),
                'action_url': error_info.get('action_url'),
                'error_code': error_info.get('error_code')
            }), 400
        
        response_data = response.json()
        print(f"レスポンスデータ: {json.dumps(response_data, indent=2)[:500]}...")  # 最初の500文字だけ表示
        
        posts_data = response_data.get('data', [])
        print(f"取得した投稿数: {len(posts_data)}")
        
        # 期間指定がある場合、投稿をフィルタリング
        if start_date and end_date:
            start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
            end_dt = datetime.fromisoformat(f"{end_date}T23:59:59+00:00")
            
            filtered_posts = []
            for post in posts_data:
                if 'timestamp' in post:
                    try:
                        post_dt = datetime.fromisoformat(post['timestamp'].replace('Z', '+00:00'))
                        if start_dt <= post_dt <= end_dt:
                            filtered_posts.append(post)
                    except Exception as e:
                        print(f"タイムスタンプ変換エラー: {e}")
                        continue
            
            posts_data = filtered_posts
            print(f"期間フィルタリング後の投稿数: {len(posts_data)}")
        
        # ページネーション情報を取得
        paging = response_data.get('paging', {})
        print(f"ページネーション情報: {paging}")
        
        return jsonify({
            'success': True,
            'posts': posts_data,
            'paging': paging
        })
        
    except Exception as e:
        import traceback
        print(f"Instagram投稿取得中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch Instagram posts: {str(e)}'}), 500

@api_bp.route('/import/instagram/analyze', methods=['POST'])
def analyze_instagram_posts():
    """Instagram投稿からスポット候補を生成するAPI"""
    if not current_user.is_authenticated:
        print("DEBUG: User not authenticated")
        return jsonify({'error': 'Authentication required'}), 401
    
    # リクエストからパラメータを取得
    data = request.get_json() or {}
    posts = data.get('posts', [])
    
    print(f"DEBUG: Received {len(posts)} posts for analysis")
    
    if not posts:
        print("DEBUG: No posts provided")
        return jsonify({'error': 'No posts provided'}), 400

    if not OPENAI_API_KEY:
        print("DEBUG: OpenAI API key not configured")
        return jsonify({'error': 'OpenAI API key not configured'}), 500

    try:
        import openai
        from openai import OpenAI
        
        # OpenAIクライアントの初期化（タイムアウト設定付き）
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=30.0  # 30秒のタイムアウト
        )
        print(f"DEBUG: OpenAI API key set: {OPENAI_API_KEY[:5]}...{OPENAI_API_KEY[-5:]}")
        
        spot_candidates = []
        
        # 処理する投稿数を制限（最初の5件のみ）
        posts_to_process = posts[:5]
        print(f"DEBUG: Processing only the first {len(posts_to_process)} posts")
        
        for post in posts_to_process:
            caption = post.get('caption', '')
            print(f"DEBUG: Processing post ID: {post.get('id')}, Caption length: {len(caption)}")
            
            # キャプションが空の場合はスキップ
            if not caption:
                print("DEBUG: Empty caption, skipping")
                continue
            
            # キャプションが長すぎる場合は切り詰める
            if len(caption) > 1000:
                caption = caption[:1000] + "..."
                print("DEBUG: Caption truncated to 1000 characters")
            
            # OpenAI APIを使用してキャプションからスポット名を抽出
            prompt = f"""
            以下のInstagramキャプションから、実際に訪問した具体的な施設名・店舗名・観光スポット名を抽出してください。
            複数の施設を訪問している場合は、すべて抽出してください。

            抽出対象：
            - レストラン、カフェ、バーなどの飲食店
            - ホテル、旅館、民宿などの宿泊施設  
            - 観光地、テーマパーク、美術館などの観光施設
            - ショップ、百貨店などの商業施設

            除外対象：
            - 都道府県名、市区町村名（例：東京都、渋谷区、藤沢市）
            - 駅名、空港名
            - 一般的な地名（例：湘南、関東地方）

            複合表現の処理：
            - 「○○の△△ホテル」→「○○ △△」として抽出
            - ブランド名は保持（例：「星野リゾート」「リッツカールトン」）
            
            キャプション: {caption}
            
            出力形式をJSON形式で返してください:
            {{
              "spots": [
                "施設名1",
                "施設名2",
                ...
              ]
            }}
            """
            
            print("DEBUG: Calling OpenAI API")
            try:
                # タイムアウト付きでAPIを呼び出す
                response = client.chat.completions.create(
                    model="gpt-4o",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "あなたはInstagramの投稿からスポット情報を抽出する専門家です。日本語のキャプションから場所名を正確に抽出してください。"},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=500  # トークン数を制限
                )
                print(f"DEBUG: OpenAI API response received")
            except Exception as openai_error:
                print(f"DEBUG: OpenAI API error: {str(openai_error)}")
                # エラーが発生した場合でも処理を続行
                # 位置情報があれば使用
                location = post.get('location', {})
                if location and 'name' in location:
                    spot_name = location.get('name')
                    print(f"DEBUG: Using location from post metadata: {spot_name}")
                    
                    # 位置情報からスポット候補を追加
                    spot_candidate = {
                        'name': spot_name,
                        'formatted_address': '',
                        'instagram_post_id': post.get('id'),
                        'instagram_permalink': post.get('permalink'),
                        'instagram_caption': caption[:100] + "..." if len(caption) > 100 else caption,
                        'timestamp': post.get('timestamp')  # タイムスタンプを明示的に追加
                    }
                    spot_candidates.append(spot_candidate)
                    print(f"DEBUG: Added spot candidate from location metadata: {spot_name}")
                
                continue
            
            try:
                # レスポンスからスポット名のリストを取得
                content = response.choices[0].message.content
                print(f"DEBUG: OpenAI response content: {content}")
                result = json.loads(content)
                print(f"DEBUG: Parsed JSON result: {result}")
                
                # スポット名を抽出（様々な形式に対応）
                spot_names = []
                
                # 辞書型の場合
                if isinstance(result, dict):
                    # 辞書の値を確認
                    for key, value in result.items():
                        # リスト型の値の場合
                        if isinstance(value, list):
                            spot_names.extend(value)
                        # 文字列型の値の場合（キーがerrorでない場合のみ）
                        elif isinstance(value, str) and not key.lower() in ['error', 'エラー']:
                            spot_names.append(value)
                        # 辞書型の値の場合（再帰的に処理）
                        elif isinstance(value, dict):
                            for sub_key, sub_value in value.items():
                                if isinstance(sub_value, str) and not sub_key.lower() in ['error', 'エラー']:
                                    spot_names.append(sub_value)
                
                # リスト型の場合
                elif isinstance(result, list):
                    spot_names = result
                
                print(f"DEBUG: Extracted spot names: {spot_names}")
                
                # 位置情報があれば優先的に使用
                location = post.get('location', {})
                if location and 'name' in location:
                    spot_names.insert(0, location.get('name'))
                    print(f"DEBUG: Added location from post metadata: {location.get('name')}")
                
                # 重複を削除
                spot_names = list(dict.fromkeys(spot_names))
                print(f"DEBUG: Final spot names after deduplication: {spot_names}")
                
                # スポット名が空の場合はスキップ
                if not spot_names:
                    print("DEBUG: No spot names found, skipping Google Places API calls")
                    continue
                
                # 各スポット名でGoogle Places APIを呼び出して詳細情報を取得
                for spot_name in spot_names:
                    # スポット名が空の場合はスキップ
                    if not spot_name or spot_name.strip() == "":
                        print("DEBUG: Empty spot name, skipping")
                        continue
                        
                    print(f"DEBUG: Looking up spot: {spot_name}")
                    
                    # 基本的なスポット候補を作成（APIエラー時のフォールバック用）
                    basic_spot_candidate = {
                        'name': spot_name,
                        'formatted_address': '',
                        'instagram_post_id': post.get('id'),
                        'instagram_permalink': post.get('permalink'),
                        'instagram_caption': caption[:100] + "..." if len(caption) > 100 else caption,
                        'timestamp': post.get('timestamp')  # タイムスタンプを明示的に追加
                    }
                    
                    print(f"DEBUG: 基本スポット候補を作成: name={basic_spot_candidate['name']}, instagram_post_id={basic_spot_candidate['instagram_post_id']}, timestamp={basic_spot_candidate['timestamp']}")
                    
                    # Google Places APIの検索エンドポイントを呼び出す
                    search_url = "https://places.googleapis.com/v1/places:searchText"
                    headers = {
                        'Content-Type': 'application/json',
                        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                        'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.location,places.types,places.id',
                        'X-Goog-LanguageCode': 'ja',  # 日本語を指定
                        'User-Agent': 'my-map.link App (https://my-map.link)'
                    }
                    search_data = {
                        "textQuery": spot_name,
                        "languageCode": "ja",  # 日本語を指定
                        "regionCode": "JP"     # 日本の地域コードを指定
                    }
                    
                    print(f"DEBUG: Calling Google Places API with query: {spot_name}")
                    try:
                        # タイムアウト設定付きでAPIを呼び出す
                        search_response = requests.post(search_url, headers=headers, json=search_data, timeout=10)
                        print(f"DEBUG: Google Places API response status: {search_response.status_code}")
                        
                        if search_response.status_code == 200:
                            search_result = search_response.json()
                            places = search_result.get('places', [])
                            
                            if places:
                                place = places[0]  # 最初の結果を使用
                                print(f"DEBUG: Found place: {place.get('displayName', {}).get('text')}")
                                
                                # スポット候補を追加
                                spot_candidate = {
                                    'name': place.get('displayName', {}).get('text', spot_name),
                                    'formatted_address': place.get('formattedAddress', ''),
                                    'latitude': place.get('location', {}).get('latitude'),
                                    'longitude': place.get('location', {}).get('longitude'),
                                    'types': place.get('types', []),
                                    'place_id': place.get('id'),
                                    'instagram_post_id': post.get('id'),
                                    'instagram_permalink': post.get('permalink'),
                                    'instagram_caption': caption[:100] + "..." if len(caption) > 100 else caption,
                                    'timestamp': post.get('timestamp')  # タイムスタンプを明示的に追加
                                }
                                
                                print(f"DEBUG: スポット候補を作成: name={spot_candidate['name']}, instagram_post_id={spot_candidate['instagram_post_id']}, timestamp={spot_candidate['timestamp']}")
                                
                                # 写真情報を取得
                                try:
                                    photo_url = f"https://places.googleapis.com/v1/places/{place.get('id')}/photos"
                                    photo_headers = {
                                        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                                        'X-Goog-FieldMask': 'photos.name,photos.widthPx,photos.heightPx'
                                    }
                                    
                                    photo_response = requests.get(photo_url, headers=photo_headers, timeout=10)
                                    
                                    if photo_response.status_code == 200:
                                        photo_data = photo_response.json()
                                        photos = photo_data.get('photos', [])
                                        
                                        if photos and len(photos) > 0:
                                            photo_name = photos[0].get('name')
                                            if photo_name:
                                                # 写真参照情報を設定
                                                spot_candidate['photo_reference'] = photo_name
                                                # サムネイルURLを設定
                                                spot_candidate['thumbnail_url'] = f"https://places.googleapis.com/v1/{photo_name}/media?key={GOOGLE_MAPS_API_KEY}&maxHeightPx=400&maxWidthPx=400"
                                                print(f"DEBUG: Added photo reference: {photo_name}")
                                except Exception as photo_error:
                                    print(f"DEBUG: Error fetching photos: {str(photo_error)}")
                                
                                # 詳細情報を取得して、日本語のsummary_locationを生成
                                try:
                                    # Google Places APIの詳細エンドポイントを呼び出す
                                    details_url = f"https://places.googleapis.com/v1/places/{place.get('id')}"
                                    details_headers = {
                                        'Content-Type': 'application/json',
                                        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                                        'X-Goog-FieldMask': 'addressComponents',
                                        'X-Goog-LanguageCode': 'ja',  # 日本語を指定
                                        'User-Agent': 'my-map.link App (https://my-map.link)'
                                    }
                                    
                                    details_response = requests.get(details_url, headers=details_headers)
                                    
                                    if details_response.status_code == 200:
                                        details_data = details_response.json()
                                        
                                        if 'addressComponents' in details_data:
                                            country = None
                                            prefecture = None
                                            locality = None
                                            
                                            for component in details_data['addressComponents']:
                                                types = component.get('types', [])
                                                if 'country' in types:
                                                    country = component.get('longText')
                                                elif 'administrative_area_level_1' in types:
                                                    prefecture = component.get('longText')
                                                elif 'locality' in types or 'sublocality_level_1' in types:
                                                    locality = component.get('longText')
                                            
                                            # サマリーロケーションを構築
                                            summary_parts = []
                                            if country and country != "日本":
                                                summary_parts.append(country)
                                            if prefecture:
                                                summary_parts.append(prefecture)
                                            if locality:
                                                summary_parts.append(locality)
                                            
                                            if summary_parts:
                                                spot_candidate['summary_location'] = '、'.join(summary_parts)
                                                print(f"DEBUG: Updated summary location from address components: {spot_candidate['summary_location']}")
                                except Exception as details_error:
                                    print(f"DEBUG: Error fetching place details: {str(details_error)}")
                                
                                # 日本語のsummary_locationが取得できなかった場合、searchTextエンドポイントを使用
                                if not spot_candidate.get('summary_location') or not is_japanese(spot_candidate.get('summary_location', '')):
                                    try:
                                        print(f"DEBUG: Using searchText endpoint to get Japanese information for: {spot_name}")
                                        
                                        search_url = "https://places.googleapis.com/v1/places:searchText"
                                        search_headers = {
                                            'Content-Type': 'application/json',
                                            'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                                            'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.addressComponents'
                                        }
                                        search_data = {
                                            'textQuery': spot_name,
                                            'languageCode': 'ja',
                                            'regionCode': 'jp'
                                        }
                                        
                                        search_response = requests.post(search_url, headers=search_headers, json=search_data, timeout=10)
                                        
                                        if search_response.status_code == 200:
                                            search_data = search_response.json()
                                            
                                            if 'places' in search_data and len(search_data['places']) > 0:
                                                place = search_data['places'][0]
                                                
                                                # サマリーロケーションを生成
                                                if 'addressComponents' in place:
                                                    country = None
                                                    prefecture = None
                                                    locality = None
                                                    
                                                    for component in place['addressComponents']:
                                                        types = component.get('types', [])
                                                        if 'country' in types:
                                                            country = component.get('longText')
                                                        elif 'administrative_area_level_1' in types:
                                                            prefecture = component.get('longText')
                                                        elif 'locality' in types or 'sublocality_level_1' in types:
                                                            locality = component.get('longText')
                                                    
                                                    # サマリーロケーションを構築
                                                    summary_parts = []
                                                    if country and country != "日本":
                                                        summary_parts.append(country)
                                                    if prefecture:
                                                        summary_parts.append(prefecture)
                                                    if locality:
                                                        summary_parts.append(locality)
                                                    
                                                    if summary_parts:
                                                        spot_candidate['summary_location'] = '、'.join(summary_parts)
                                                        print(f"DEBUG: Set Japanese summary_location from searchText: {spot_candidate['summary_location']}")
                                    except Exception as search_error:
                                        print(f"DEBUG: Error calling searchText API: {str(search_error)}")
                                
                                spot_candidates.append(spot_candidate)
                                print(f"DEBUG: Added spot candidate: {spot_candidate['name']}")
                            else:
                                print(f"DEBUG: No places found for spot name: {spot_name}")
                                # 場所が見つからない場合でも、名前だけのスポット候補を追加
                                spot_candidates.append(basic_spot_candidate)
                                print(f"DEBUG: Added basic spot candidate with name only: {spot_name}")
                        else:
                            print(f"DEBUG: Google Places API error: {search_response.text}")
                            # APIエラーの場合でも、名前だけのスポット候補を追加
                            spot_candidates.append(basic_spot_candidate)
                            print(f"DEBUG: Added basic spot candidate after API error: {spot_name}")
                    except Exception as google_error:
                        print(f"DEBUG: Google Places API error: {str(google_error)}")
                        # 例外発生時も、名前だけのスポット候補を追加
                        spot_candidates.append(basic_spot_candidate)
                        print(f"DEBUG: Added basic spot candidate after exception: {spot_name}")
                        continue
            
            except Exception as e:
                print(f"DEBUG: Error processing post {post.get('id')}: {str(e)}")
                continue
        
        print(f"DEBUG: Analysis complete. Found {len(spot_candidates)} spot candidates")
        return jsonify({
            'success': True,
            'count': len(spot_candidates),
            'spot_candidates': spot_candidates
        })
        
    except Exception as e:
        print(f"DEBUG: Failed to analyze Instagram posts: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to analyze Instagram posts: {str(e)}'}), 500

@api_bp.route('/import/instagram/save', methods=['POST'])
def save_instagram_spots():
    """選択されたスポット候補を保存するAPI"""
    print("=== Instagram投稿保存API開始 ===")
    if not current_user.is_authenticated:
        print("エラー: 認証されていないユーザー")
        return jsonify({'error': 'Authentication required'}), 401
    
    # リクエストからパラメータを取得
    data = request.get_json() or {}
    spot_candidates = data.get('spot_candidates', [])
    
    print(f"保存するスポット候補数: {len(spot_candidates)}")
    
    if not spot_candidates:
        print("エラー: スポット候補が提供されていません")
        return jsonify({'error': 'No spot candidates provided'}), 400
    
    try:
        saved_spots = []
        
        # スポット候補の情報をログに出力
        for i, spot_data in enumerate(spot_candidates):
            print(f"スポット候補 {i+1}/{len(spot_candidates)}: {spot_data.get('name', 'Unknown')}")
            print(f"  - instagram_post_id: {spot_data.get('instagram_post_id')}")
            print(f"  - timestamp: {spot_data.get('timestamp')}")
            print(f"  - types: {spot_data.get('types', [])}")
            print(f"  - formatted_address: {spot_data.get('formatted_address', '')}")
            print(f"  - photo_reference: {spot_data.get('photo_reference', '')}")
            print(f"  - summary_location: {spot_data.get('summary_location', '')}")
        
        for spot_data in spot_candidates:
            # スポットの基本情報を設定
            spot = Spot(
                user_id=current_user.id,
                name=spot_data.get('name'),
                description='',  # デフォルトを空文字列に設定
                location=spot_data.get('formatted_address', ''),
                latitude=spot_data.get('latitude'),
                longitude=spot_data.get('longitude'),
                category=spot_data.get('types', [])[0] if spot_data.get('types') else None,
                google_place_id=spot_data.get('place_id'),
                formatted_address=spot_data.get('formatted_address', ''),
                summary_location=spot_data.get('summary_location', ''),
                thumbnail_url=spot_data.get('thumbnail_url', ''),
                is_active=False  # 非公開状態で保存
            )
            
            print(f"スポットモデル作成: {spot.name}, user_id={spot.user_id}")
            print(f"  - formatted_address: {spot.formatted_address}")
            print(f"  - google_place_id: {spot.google_place_id}")
            print(f"  - summary_location: {spot.summary_location}")
            
            # Google Placesのtypesから日本語カテゴリを生成
            if 'types' in spot_data and spot_data['types']:
                try:
                    spot.types = json.dumps(spot_data['types'])
                    print(f"タイプ情報設定: {spot.types}")
                except Exception as e:
                    print(f"types設定エラー: {str(e)}")
                    spot.types = json.dumps([])
                
                # OpenAI APIを使用して日本語カテゴリを生成
                if OPENAI_API_KEY:
                    try:
                        import openai
                        from openai import OpenAI
                        
                        # OpenAIクライアントの初期化（タイムアウト設定付き）
                        client = OpenAI(
                            api_key=OPENAI_API_KEY,
                            timeout=30.0  # 30秒のタイムアウト
                        )
                        
                        types_str = ", ".join(spot_data['types'])
                        
                        prompt = f"""
                        以下のGoogle Places APIから返されたタイプ情報から、最も適切な日本語のカテゴリ名を1つだけ生成してください。
                        
                        タイプ情報: {types_str}
                        
                        以下のようなカテゴリを参考にしてください：
                        - レストラン
                        - カフェ
                        - バー
                        - ショッピング
                        - 観光スポット
                        - 公園
                        - 美術館・博物館
                        - ホテル
                        - エンターテイメント
                        - スポーツ施設
                        - その他
                        
                        日本語カテゴリ名:
                        """
                        
                        print(f"OpenAI APIを呼び出してカテゴリを生成")
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": "あなたはGoogle Placesのタイプ情報から適切な日本語カテゴリを生成する専門家です。"},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=50  # カテゴリ名は短いので少ないトークン数で十分
                        )
                        
                        category = response.choices[0].message.content.strip()
                        spot.category = category
                        print(f"生成されたカテゴリ: {category}")
                    except Exception as e:
                        print(f"カテゴリ生成エラー: {str(e)}")
                        spot.category = "その他"
            
            # 日本語のsummary_locationを取得
            if spot_data.get('place_id') and (not spot.summary_location or spot.summary_location == ''):
                try:
                    print(f"日本語のsummary_locationを取得: place_id={spot_data.get('place_id')}")
                    
                    # Google Places APIの詳細エンドポイントを呼び出す
                    details_url = f"https://places.googleapis.com/v1/places/{spot_data.get('place_id')}"
                    details_headers = {
                        'Content-Type': 'application/json',
                        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                        'X-Goog-FieldMask': 'addressComponents',
                        'X-Goog-LanguageCode': 'ja',  # 日本語を指定
                        'User-Agent': 'my-map.link App (https://my-map.link)'
                    }
                    
                    details_response = requests.get(details_url, headers=details_headers)
                    
                    if details_response.status_code == 200:
                        details_data = details_response.json()
                        
                        if 'addressComponents' in details_data:
                            country = None
                            prefecture = None
                            locality = None
                            
                            for component in details_data['addressComponents']:
                                types = component.get('types', [])
                                if 'country' in types:
                                    country = component.get('longText')
                                elif 'administrative_area_level_1' in types:
                                    prefecture = component.get('longText')
                                elif 'locality' in types or 'sublocality_level_1' in types:
                                    locality = component.get('longText')
                            
                            # サマリーロケーションを構築
                            summary_parts = []
                            if country and country != "日本":
                                summary_parts.append(country)
                            if prefecture:
                                summary_parts.append(prefecture)
                            if locality:
                                summary_parts.append(locality)
                            
                            if summary_parts:
                                spot.summary_location = '、'.join(summary_parts)
                                print(f"日本語のsummary_locationを設定: {spot.summary_location}")
                    else:
                        print(f"Google Places API詳細取得エラー: ステータスコード {details_response.status_code}")
                        print(f"レスポンス: {details_response.text}")
                except Exception as e:
                    print(f"summary_location取得エラー: {str(e)}")
            
            # 日本語のsummary_locationが取得できなかった場合、searchTextエンドポイントを使用
            if spot_data.get('place_id') and (not spot.summary_location or not is_japanese(spot.summary_location)):
                try:
                    print(f"searchTextエンドポイントを使用して日本語情報を取得: {spot.name}")
                    
                    search_url = "https://places.googleapis.com/v1/places:searchText"
                    search_headers = {
                        'Content-Type': 'application/json',
                        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                        'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.addressComponents'
                    }
                    search_data = {
                        'textQuery': spot.name,
                        'languageCode': 'ja',
                        'regionCode': 'jp'
                    }
                    
                    search_response = requests.post(search_url, headers=search_headers, json=search_data)
                    
                    if search_response.status_code == 200:
                        search_data = search_response.json()
                        
                        if 'places' in search_data and len(search_data['places']) > 0:
                            place = search_data['places'][0]
                            
                            # サマリーロケーションを生成
                            if 'addressComponents' in place:
                                country = None
                                prefecture = None
                                locality = None
                                
                                for component in place['addressComponents']:
                                    types = component.get('types', [])
                                    if 'country' in types:
                                        country = component.get('longText')
                                    elif 'administrative_area_level_1' in types:
                                        prefecture = component.get('longText')
                                    elif 'locality' in types or 'sublocality_level_1' in types:
                                        locality = component.get('longText')
                                
                                # サマリーロケーションを構築
                                summary_parts = []
                                if country and country != "日本":
                                    summary_parts.append(country)
                                if prefecture:
                                    summary_parts.append(prefecture)
                                if locality:
                                    summary_parts.append(locality)
                                
                                if summary_parts:
                                    spot.summary_location = '、'.join(summary_parts)
                                    print(f"searchTextから日本語のsummary_locationを設定: {spot.summary_location}")
                            
                            # フォーマット済み住所が取得できたら更新
                            if 'formattedAddress' in place and place['formattedAddress'] and not spot.formatted_address:
                                spot.formatted_address = place['formattedAddress']
                                print(f"searchTextからformatted_addressを更新: {spot.formatted_address}")
                except Exception as e:
                    print(f"searchText API呼び出しエラー: {str(e)}")
            
            # レビュー要約の取得（editorialSummary → reviewSummary 優先）
            try:
                if spot.google_place_id and (not getattr(spot, 'review_summary', None) or not spot.review_summary):
                    # 直接 Places v1 を叩いて最小フィールドで取得
                    details_url = f"https://places.googleapis.com/v1/places/{spot.google_place_id}"
                    details_headers = {
                        'Content-Type': 'application/json',
                        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                        'X-Goog-FieldMask': 'editorialSummary,reviewSummary',
                        'X-Goog-LanguageCode': 'ja',
                        'User-Agent': 'my-map.link App (https://my-map.link)'
                    }
                    rs_resp = requests.get(details_url, headers=details_headers, params={'languageCode': 'ja'}, timeout=8)
                    if rs_resp.status_code == 200:
                        rs_data = rs_resp.json() if rs_resp.content else {}
                        review_summary_text = None
                        editorial = rs_data.get('editorialSummary')
                        if isinstance(editorial, dict):
                            txt = editorial.get('text')
                            if isinstance(txt, str) and txt.strip():
                                review_summary_text = txt.strip()
                        elif isinstance(editorial, str) and editorial.strip():
                            review_summary_text = editorial.strip()
                        if not review_summary_text:
                            rs = rs_data.get('reviewSummary')
                            if isinstance(rs, dict):
                                txt = rs.get('text')
                                if isinstance(txt, str) and txt.strip():
                                    review_summary_text = txt.strip()
                                else:
                                    overview = rs.get('overview') if isinstance(rs.get('overview'), dict) else None
                                    if overview and isinstance(overview.get('text'), str) and overview.get('text').strip():
                                        review_summary_text = overview.get('text').strip()
                            elif isinstance(rs, str) and rs.strip():
                                review_summary_text = rs.strip()
                        if review_summary_text:
                            spot.review_summary = review_summary_text
            except Exception as _:
                pass

            print(f"スポットをデータベースに追加")
            spot_info = {
                'name': spot.name,
                'category': spot.category,
                'formatted_address': spot.formatted_address,
                'types': spot.types,
                'summary_location': spot.summary_location,
                'google_place_id': spot.google_place_id,
                'instagram_post_id': spot_data.get('instagram_post_id'),
                'instagram_permalink': spot_data.get('instagram_permalink')
            }
            saved_spots.append(spot_info)
            db.session.add(spot)
            db.session.flush()  # IDを取得するためのフラッシュ
            print(f"スポットID: {spot.id}")
            
            # 🆕 Instagram投稿との紐付けを追加
            if spot_data.get('instagram_permalink'):
                try:
                    social_post = SocialPost(
                        user_id=current_user.id,
                        spot_id=spot.id,
                        platform='instagram',
                        post_url=spot_data.get('instagram_permalink')
                    )
                    db.session.add(social_post)
                    print(f"Instagram投稿を紐付け: {spot_data.get('instagram_permalink')}")
                except Exception as e:
                    print(f"Instagram投稿紐付けエラー: {str(e)}")
            
            # 🆕 インポート履歴の保存
            if spot_data.get('instagram_post_id'):
                try:
                    import_history = ImportHistory(
                        user_id=current_user.id,
                        source='instagram',
                        external_id=spot_data.get('instagram_post_id'),
                        status='success',
                        spot_id=spot.id,
                        raw_data={
                            'caption': spot_data.get('instagram_caption'),
                            'timestamp': spot_data.get('timestamp'),
                            'permalink': spot_data.get('instagram_permalink'),
                            'post_id': spot_data.get('instagram_post_id')
                        }
                    )
                    db.session.add(import_history)
                    print(f"インポート履歴を保存: Instagram投稿ID={spot_data.get('instagram_post_id')}")
                except Exception as e:
                    print(f"インポート履歴保存エラー: {str(e)}")
            
            # Google Place IDは保存済み - 写真は表示時に動的取得
            print(f"Google Place ID保存完了: {spot.google_place_id}")
            print("写真は表示時にGoogle Photos Serviceで動的取得されます")
            
            # 楽天トラベルアフィリエイトリンクの自動生成（仕様変更のため一時停止）
            # if current_user.rakuten_affiliate_id and spot.name:
            #     try:
            #         print(f"楽天トラベルAPI検索: {spot.name}")
            #         hotel_results = search_hotel_with_fallback(spot.name, current_user.rakuten_affiliate_id)
            #         if hotel_results.get('error') == 'no_hotels_found':
            #             print(f"楽天トラベル: '{spot.name}'に該当するホテルが見つかりませんでした")
            #         elif hotel_results.get('error'):
            #             print(f"楽天トラベルAPIエラー: {hotel_results.get('message', 'Unknown error')}")
            #         elif 'hotels' in hotel_results and len(hotel_results['hotels']) > 0:
            #             print(f"ホテル検索結果: {len(hotel_results['hotels'])}件見つかりました")
            #             selected_hotel = select_best_hotel_with_evaluation(spot.name, hotel_results)
            #             if selected_hotel:
            #                 if 'hotel' in selected_hotel and len(selected_hotel['hotel']) > 0:
            #                     hotel_info = selected_hotel['hotel'][0]
            #                     if 'hotelBasicInfo' in hotel_info:
            #                         basic_info = hotel_info['hotelBasicInfo']
            #                         if basic_info.get('hotelInformationUrl'):
            #                             hotel_url = basic_info.get('hotelInformationUrl')
            #                             affiliate_url = generate_rakuten_affiliate_url(
            #                                 hotel_url,
            #                                 current_user.rakuten_affiliate_id
            #                             )
            #                             affiliate_link = AffiliateLink(
            #                                 spot_id=spot.id,
            #                                 platform='rakuten',
            #                                 url=affiliate_url,
            #                                 title='楽天トラベル',
            #                                 description='楽天トラベルで予約 (PRを含む)',
            #                                 icon_key='rakuten-travel',
            #                                 is_active=True
            #                             )
            #                             db.session.add(affiliate_link)
            #     except Exception as e:
            #         print(f"楽天トラベルアフィリエイトリンク生成エラー: {str(e)}")
        
        print(f"データベースに変更をコミット")
        db.session.commit()
        
        print(f"コミット成功: {len(saved_spots)}件のスポットを保存")
        
        return jsonify({
            'success': True,
            'count': len(saved_spots),
            'saved_spots': saved_spots
        })
        
    except Exception as e:
        print(f"保存処理エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': f'Failed to save spots: {str(e)}'}), 500

@api_bp.route('/import/instagram/save-async', methods=['POST'])
@login_required
def start_instagram_save():
    """Instagramスポット保存の非同期タスクを開始する"""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json() or {}
    spot_candidates = data.get('spot_candidates', [])
    user_id = current_user.id
    
    if not spot_candidates:
        return jsonify({'error': 'No spot candidates provided'}), 400
    
    try:
        # Redis接続とキューのセットアップ
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        
        # ローカル開発環境ではSSL設定を無効化
        if 'localhost' in redis_url or '127.0.0.1' in redis_url:
            redis_conn = Redis.from_url(redis_url)
        else:
            # Heroku等の本番環境ではSSL証明書検証を無効化
            redis_conn = Redis.from_url(redis_url, ssl_cert_reqs=None)
        
        q = Queue(connection=redis_conn)
        
        # 重複実行制御: 15分以内の実行中の保存ジョブがあるかチェック
        timeout_threshold = datetime.utcnow() - timedelta(minutes=15)
        progress = ImportProgress.query.filter_by(
            user_id=user_id, 
            source='instagram'
        ).first()
        
        if progress and progress.save_status in ['pending', 'processing']:
            # 15分以内の場合のみ重複と判定
            if progress.last_imported_at > timeout_threshold:
                return jsonify({
                    'error': 'Save job already in progress. Please wait for the current job to complete.',
                    'existing_save_job_id': progress.save_job_id,
                    'existing_save_status': progress.save_status
                }), 409
            else:
                # 15分以上経過している場合は、古いジョブを無効にする
                print(f"15分以上経過した保存ジョブを無効化: save_job_id={progress.save_job_id}")
                progress.save_status = 'failed'
                progress.save_error_info = 'Timeout: Job was running for more than 15 minutes'
                db.session.commit()
        
        # 既存のImportProgressレコードを取得または作成
        if not progress:
            progress = ImportProgress(
                user_id=user_id,
                source='instagram'
            )
            db.session.add(progress)
            db.session.flush()  # IDを取得
        
        # 保存ジョブの情報を設定
        save_job_id = str(uuid.uuid4())
        progress.save_job_id = save_job_id
        progress.save_status = 'pending'
        progress.save_error_info = None
        progress.save_result_data = None
        db.session.commit()
        
        print(f"保存ジョブを開始: save_job_id={save_job_id}, user_id={user_id}, candidates={len(spot_candidates)}")
        
        # 非同期タスクをキューに追加
        job = q.enqueue(
            save_spots_async,
            save_job_id=save_job_id,
            user_id=user_id,
            spot_candidates=spot_candidates,
            job_timeout=300  # 5分のタイムアウト
        )
        
        return jsonify({
            'success': True,
            'save_job_id': save_job_id,
            'message': f'{len(spot_candidates)}件のスポット保存処理を開始しました。'
        })
        
    except Exception as e:
        print(f"保存ジョブ開始エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # エラーが発生した場合、DBの状態を更新
        if 'progress' in locals() and progress:
            progress.save_status = 'failed'
            progress.save_error_info = str(e)
            db.session.commit()
        
        return jsonify({'error': f'Failed to start save job: {str(e)}'}), 500

@api_bp.route('/import/instagram/save-status/<string:save_job_id>', methods=['GET'])
@login_required
def get_save_status(save_job_id):
    """保存ジョブのステータスを取得する"""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        # ImportProgressテーブルから保存ジョブの情報を取得
        progress = ImportProgress.query.filter_by(
            save_job_id=save_job_id,
            user_id=current_user.id
        ).first()
        
        if not progress:
            return jsonify({'error': 'Save job not found'}), 404
        
        result = {
            'save_job_id': save_job_id,
            'status': progress.save_status,
            'error_info': progress.save_error_info
        }
        
        # 完了した場合は結果データも含める
        if progress.save_status == 'completed' and progress.save_result_data:
            try:
                result['result_data'] = json.loads(progress.save_result_data)
            except json.JSONDecodeError:
                result['result_data'] = {}
        
        return jsonify(result)
        
    except Exception as e:
        print(f"保存ステータス取得エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to get save status: {str(e)}'}), 500

@api_bp.route('/import/instagram/start', methods=['POST'])
@login_required
def start_instagram_import():
    """Instagramインポートの非同期タスクを開始する"""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    user_id = current_user.id  # ログイン中のユーザーIDを使用

    if not all([start_date, end_date]):
        return jsonify({'error': 'Start date and end date are required.'}), 400

    try:
        # Redis接続とキューのセットアップ（ローカル開発環境でのSSLエラーを回避）
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        
        # ローカル開発環境ではSSL設定を無効化
        if 'localhost' in redis_url or '127.0.0.1' in redis_url:
            redis_conn = Redis.from_url(redis_url)
        else:
            # Heroku等の本番環境ではSSL証明書検証を無効化
            redis_conn = Redis.from_url(redis_url, ssl_cert_reqs=None)
        
        q = Queue(connection=redis_conn)

        # 重複実行制御: 15分以内の実行中のジョブがあるかチェック
        timeout_threshold = datetime.utcnow() - timedelta(minutes=15)
        existing_running_job = ImportProgress.query.filter_by(
            user_id=user_id, 
            source='instagram'
        ).filter(
            ImportProgress.status.in_(['pending', 'processing']),
            ImportProgress.last_imported_at > timeout_threshold  # 15分以内のもののみ
        ).first()
        
        if existing_running_job:
            return jsonify({
                'error': 'Import job already in progress. Please wait for the current job to complete.',
                'existing_job_id': existing_running_job.job_id,
                'existing_status': existing_running_job.status,
                'timeout_info': '15分経過後に自動的にリセットされます'
            }), 409  # Conflict status code
        
        # 既存の完了/失敗したインポート進捗レコードを検索
        progress = ImportProgress.query.filter_by(user_id=user_id, source='instagram').first()
        
        job_id = str(uuid.uuid4())

        if progress:
            # 既存のレコードがあれば更新（実行中でない場合のみここに到達）
            progress.job_id = job_id
            progress.status = 'pending'
            progress.import_period_start = datetime.fromisoformat(start_date)
            progress.import_period_end = datetime.fromisoformat(end_date)
            progress.error_info = None
            progress.result_data = None
        else:
            # 新しいジョブエントリをDBに作成
            progress = ImportProgress(
                user_id=user_id,
                source='instagram',
                job_id=job_id,
                status='pending',
                import_period_start=datetime.fromisoformat(start_date),
                import_period_end=datetime.fromisoformat(end_date)
            )
            db.session.add(progress)

        db.session.commit()

        # タスクをキューに追加
        q.enqueue(
            fetch_and_analyze_posts,
            args=[job_id, user_id, start_date, end_date],
            job_timeout=600, # 10分でタイムアウト
            job_id=job_id
        )
        
        return jsonify({'success': True, 'job_id': job_id}), 202

    except Exception as e:
        import traceback
        current_app.logger.error(f"Error starting Instagram import job: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to start import job.'}), 500

@api_bp.route('/import/instagram/status/<string:job_id>', methods=['GET'])
@login_required
def get_import_status(job_id):
    """非同期インポートタスクのステータスを確認する"""
    # セキュリティ: 認証チェック
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        # セキュリティ: 自分のジョブのみアクセス可能
        progress = ImportProgress.query.filter_by(
            job_id=job_id, 
            user_id=current_user.id  # 重要: ユーザーIDでフィルタして他ユーザーのジョブを参照不可
        ).first_or_404()
        
        response_data = {
            'job_id': progress.job_id,
            'status': progress.status,
        }
        
        if progress.status == 'completed':
            response_data['result_data'] = json.loads(progress.result_data) if progress.result_data else {}
        elif progress.status == 'failed':
            response_data['error_info'] = progress.error_info
            
        return jsonify(response_data)

    except Exception as e:
        current_app.logger.error(f"Error fetching import status for job {job_id}: {e}")
        return jsonify({'error': 'Failed to get import status.'}), 500

@api_bp.route('/import/instagram/cancel/<string:job_id>', methods=['POST'])
@login_required
def cancel_import_job(job_id):
    """インポートジョブをキャンセルする"""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        # Redis接続の設定
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        
        if 'localhost' in redis_url or '127.0.0.1' in redis_url:
            redis_conn = Redis.from_url(redis_url)
        else:
            redis_conn = Redis.from_url(redis_url, ssl_cert_reqs=None)
        
        # 1. RQジョブをキャンセル（エラーが発生しても続行）
        try:
            from rq.job import Job
            import rq
            
            job = Job.fetch(job_id, connection=redis_conn)
            job_status = job.get_status()
            
            if job_status in ['queued', 'started']:
                # まずjob.cancel()を試行
                try:
                    job.cancel()
                    print(f"RQジョブをキャンセルしました: {job_id}")
                except Exception as cancel_error:
                    print(f"job.cancel()エラー（rq.cancel_job()で再試行）: {cancel_error}")
                    # 失敗した場合のみrq.cancel_job()を使用
                    rq.cancel_job(job_id, connection=redis_conn)
                    print(f"rq.cancel_job関数でジョブをキャンセルしました: {job_id}")
            else:
                print(f"ジョブは既に{job_status}状態のためキャンセル不要: {job_id}")
            
        except Exception as rq_error:
            print(f"RQジョブキャンセルエラー（続行）: {rq_error}")
        
        # 2. DB状態を更新（セキュリティ: 自分のジョブのみ）
        progress = ImportProgress.query.filter_by(
            job_id=job_id,
            user_id=current_user.id
        ).first()
        
        if not progress:
            return jsonify({'error': 'Job not found'}), 404
        
        # ジョブステータスを更新
        progress.status = 'cancelled'
        progress.error_info = 'User cancelled the job'
        db.session.commit()
        
        print(f"インポートジョブをキャンセルしました: job_id={job_id}, user_id={current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'インポートジョブをキャンセルしました'
        })
        
    except Exception as e:
        print(f"インポートジョブキャンセルエラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to cancel import job: {str(e)}'}), 500

@api_bp.route('/import/instagram/cancel-save/<string:save_job_id>', methods=['POST'])
@login_required
def cancel_save_job(save_job_id):
    """保存ジョブをキャンセルする"""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        # Redis接続の設定
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        
        if 'localhost' in redis_url or '127.0.0.1' in redis_url:
            redis_conn = Redis.from_url(redis_url)
        else:
            redis_conn = Redis.from_url(redis_url, ssl_cert_reqs=None)
        
        # 1. RQジョブをキャンセル（エラーが発生しても続行）
        try:
            from rq.job import Job
            import rq
            
            job = Job.fetch(save_job_id, connection=redis_conn)
            job_status = job.get_status()
            
            if job_status in ['queued', 'started']:
                # まずjob.cancel()を試行
                try:
                    job.cancel()
                    print(f"RQ保存ジョブをキャンセルしました: {save_job_id}")
                except Exception as cancel_error:
                    print(f"job.cancel()エラー（rq.cancel_job()で再試行）: {cancel_error}")
                    # 失敗した場合のみrq.cancel_job()を使用
                    rq.cancel_job(save_job_id, connection=redis_conn)
                    print(f"rq.cancel_job関数で保存ジョブをキャンセルしました: {save_job_id}")
            else:
                print(f"保存ジョブは既に{job_status}状態のためキャンセル不要: {save_job_id}")
            
        except Exception as rq_error:
            print(f"RQ保存ジョブキャンセルエラー（続行）: {rq_error}")
        
        # 2. DB状態を更新（セキュリティ: 自分のジョブのみ）
        progress = ImportProgress.query.filter_by(
            save_job_id=save_job_id,
            user_id=current_user.id
        ).first()
        
        if not progress:
            return jsonify({'error': 'Save job not found'}), 404
        
        # 保存ジョブステータスを更新
        progress.save_status = 'cancelled'
        progress.save_error_info = 'User cancelled the save job'
        db.session.commit()
        
        print(f"保存ジョブをキャンセルしました: save_job_id={save_job_id}, user_id={current_user.id}")
        
        return jsonify({
            'success': True,
            'message': '保存ジョブをキャンセルしました'
        })
        
    except Exception as e:
        print(f"保存ジョブキャンセルエラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to cancel save job: {str(e)}'}), 500

@api_bp.route('/import/instagram/check-active-jobs', methods=['GET'])
@login_required
def check_active_jobs():
    """現在のユーザーの進行中ジョブをチェックする（復帰機能用）"""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        # 現在のユーザーの最新の ImportProgress レコードを取得
        progress = ImportProgress.query.filter_by(
            user_id=current_user.id
        ).order_by(ImportProgress.last_imported_at.desc()).first()
        
        if not progress:
            return jsonify({
                'has_active_job': False,
                'message': '進行中のジョブはありません'
            })
        
        # インポートジョブの状態をチェック
        active_import_job = None
        active_save_job = None
        
        # インポートジョブが進行中かチェック
        if progress.job_id and progress.status in ['pending', 'processing']:
            active_import_job = {
                'type': 'import',
                'job_id': progress.job_id,
                'status': progress.status,
                'created_at': progress.last_imported_at.isoformat() if progress.last_imported_at else None
            }
        
        # 保存ジョブが進行中かチェック
        if progress.save_job_id and progress.save_status in ['pending', 'processing']:
            active_save_job = {
                'type': 'save',
                'job_id': progress.save_job_id,
                'status': progress.save_status,
                'created_at': progress.last_imported_at.isoformat() if progress.last_imported_at else None
            }
        
        # どちらかのジョブが進行中の場合
        if active_import_job or active_save_job:
            response_data = {
                'has_active_job': True,
                'jobs': []
            }
            
            if active_import_job:
                response_data['jobs'].append(active_import_job)
            
            if active_save_job:
                response_data['jobs'].append(active_save_job)
            
            # 分析完了データがある場合は含める（保存ジョブ復帰時に必要）
            if progress.result_data and active_save_job:
                response_data['result_data'] = progress.result_data
            
            print(f"進行中ジョブを検出: user_id={current_user.id}, import={bool(active_import_job)}, save={bool(active_save_job)}")
            return jsonify(response_data)
        
        # 進行中のジョブがない場合
        return jsonify({
            'has_active_job': False,
            'message': '進行中のジョブはありません'
        })
        
    except Exception as e:
        print(f"進行中ジョブチェックエラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to check active jobs: {str(e)}'}), 500

# 日本語かどうかを判定する関数を追加
def is_japanese(text):
    """テキストに日本語が含まれているかを判定する"""
    if not text:
        return False
    
    # 日本語の文字コード範囲
    japanese_ranges = [
        (0x3040, 0x309F),  # ひらがな
        (0x30A0, 0x30FF),  # カタカナ
        (0x4E00, 0x9FFF),  # 漢字
        (0x3400, 0x4DBF),  # 漢字拡張A
        (0xFF00, 0xFFEF)   # 全角英数
    ]
    
    # テキスト内の各文字について日本語かどうかをチェック
    for char in text:
        char_code = ord(char)
        for start, end in japanese_ranges:
            if start <= char_code <= end:
                return True
    
    return False

@api_bp.route('/rakuten/manual-search', methods=['POST'])
@login_required
def manual_rakuten_search():
    """手動操作用の楽天ホテル検索API（完全独立）
    
    スポット登録・編集画面でユーザーが「ホテルを検索して選択」ボタンを
    クリックした際に呼び出される専用エンドポイント
    """
    if not current_user.is_authenticated:
        return jsonify({'error': '認証が必要です'}), 401
        
    if not current_user.rakuten_affiliate_id:
        return jsonify({'error': 'アフィリエイトIDが設定されていません'}), 400
    
    try:
        # リクエストデータを取得
        data = request.get_json()
        if not data:
            return jsonify({'error': 'リクエストデータが必要です'}), 400
            
        spot_name = data.get('spot_name', '').strip()
        if not spot_name:
            return jsonify({'error': 'スポット名が必要です'}), 400
        
        print(f"手動楽天検索開始: ユーザー={current_user.id}, スポット名='{spot_name}'")
        
        # 手動操作用のシンプルな検索処理（LLM評価なし）
        result = simple_hotel_search_for_manual(
            spot_name=spot_name,
            affiliate_id=current_user.rakuten_affiliate_id,
            max_results=5
        )
        
        # エラーハンドリング
        if result.get('error'):
            error_code = result.get('error')
            error_message = result.get('message', '検索中にエラーが発生しました')
            
            # 「ホテルが見つからない」は正常な結果として扱う
            if error_code == 'no_hotels_found':
                print(f"手動楽天検索結果: ホテルが見つかりませんでした")
                return jsonify({
                    'success': True,
                    'hotels': [],
                    'total_count': 0,
                    'message': '該当するホテルが見つかりませんでした'
                })
            
            # その他のエラーは400エラーとして扱う
            print(f"手動楽天検索エラー: {error_message}")
            return jsonify({
                'success': False,
                'error': error_code,
                'message': error_message
            }), 400
        
        # 成功レスポンス
        hotels = result.get('hotels', [])
        print(f"手動楽天検索完了: {len(hotels)}件の候補を取得")
        
        return jsonify({
            'success': True,
            'hotels': hotels,
            'total_count': len(hotels),
            'message': f'{len(hotels)}件のホテル候補が見つかりました'
        })
        
    except Exception as e:
        print(f"手動楽天検索API予期しないエラー: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': '検索中にエラーが発生しました。しばらく時間をおいて再度お試しください。'
        }), 500

@api_bp.route('/wallet/ingest/view', methods=['POST'])
def ingest_view():
    try:
        data = request.get_json() or {}
        user_id = int(data.get('user_id'))  # クリエイターID（公開ページ側で埋め込む）
        page_id = int(data.get('page_id'))  # spot.id
        client_id = data.get('client_id')   # 1st-party cookie（生）
        session_id = data.get('session_id') # 30分スライディング
        user_agent = request.headers.get('User-Agent', '')
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        referrer = request.referrer
        dwell_ms = int(data.get('dwell_ms') or 0)
        price_median = data.get('price_median')

        # Bot簡易判定
        ua = (user_agent or '').lower()
        bot_keywords = ['bot', 'crawl', 'spider', 'headless', 'selenium', 'python', 'curl', 'wget']
        is_bot = any(k in ua for k in bot_keywords) or 'headlesschrome' in ua
        bot_reason = None
        if is_bot:
            bot_reason = 'ua'
        if dwell_ms < 3000:
            # viewとしては無効だが、生ログは残す
            pass

        # client_key = HMAC_SHA256(salt, client_id)（生は保存しない）
        client_key = None
        if client_id:
            import hmac, hashlib
            salt = current_app.config.get('SECRET_KEY', 'salt')
            client_key = hmac.new(salt.encode('utf-8'), client_id.encode('utf-8'), hashlib.sha256).hexdigest()

        from app.models import EventLog
        from sqlalchemy.dialects.postgresql import INET
        ev = EventLog(
            user_id=user_id,
            page_id=page_id,
            event_type='view',
            client_key=client_key,
            session_id=session_id,
            user_agent=user_agent,
            ip=ip,
            referrer=referrer,
            dwell_ms=dwell_ms,
            price_median=price_median,
            is_bot=is_bot,
            bot_reason=bot_reason,
        )
        db.session.add(ev)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400


@api_bp.route('/wallet/ingest/click', methods=['POST'])
def ingest_click():
    try:
        data = request.get_json() or {}
        user_id = int(data.get('user_id'))
        page_id = int(data.get('page_id'))
        ota = data.get('ota')
        client_id = data.get('client_id')
        session_id = data.get('session_id')
        user_agent = request.headers.get('User-Agent', '')
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        referrer = request.referrer

        # client_key生成
        client_key = None
        if client_id:
            import hmac, hashlib
            salt = current_app.config.get('SECRET_KEY', 'salt')
            client_key = hmac.new(salt.encode('utf-8'), client_id.encode('utf-8'), hashlib.sha256).hexdigest()

        # Bot簡易判定
        ua = (user_agent or '').lower()
        bot_keywords = ['bot', 'crawl', 'spider', 'headless', 'selenium', 'python', 'curl', 'wget']
        is_bot = any(k in ua for k in bot_keywords) or 'headlesschrome' in ua
        bot_reason = 'ua' if is_bot else None

        from app.models import EventLog
        ev = EventLog(
            user_id=user_id,
            page_id=page_id,
            ota=ota,
            event_type='click',
            client_key=client_key,
            session_id=session_id,
            user_agent=user_agent,
            ip=ip,
            referrer=referrer,
            is_bot=is_bot,
            bot_reason=bot_reason,
        )
        db.session.add(ev)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400


@api_bp.route('/wallet/r/<string:ota>')
def wallet_redirect(ota: str):
    """クリック計測用リダイレクト。
    クエリ: user_id, page_id, url (エンコード済み)
    """
    try:
        user_id = int(request.args.get('user_id'))
        page_id = int(request.args.get('page_id'))
        dest = request.args.get('url')
        session_id = request.args.get('sid')
        client_id = request.args.get('cid')
        user_agent = request.headers.get('User-Agent', '')
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        referrer = request.referrer

        # client_key
        client_key = None
        if client_id:
            import hmac, hashlib
            salt = current_app.config.get('SECRET_KEY', 'salt')
            client_key = hmac.new(salt.encode('utf-8'), client_id.encode('utf-8'), hashlib.sha256).hexdigest()

        from app.models import EventLog
        ev = EventLog(
            user_id=user_id,
            page_id=page_id,
            ota=ota,
            event_type='click',
            client_key=client_key,
            session_id=session_id,
            user_agent=user_agent,
            ip=ip,
            referrer=referrer,
        )
        db.session.add(ev)
        db.session.commit()

        if not dest:
            return jsonify({'ok': False, 'error': 'Missing url'}), 400
        return redirect(dest, code=302)
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400