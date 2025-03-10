from flask import Blueprint, jsonify, request, abort
from app.models import Spot, Photo, AffiliateLink, SocialPost
from sqlalchemy.orm import joinedload
import requests
import os
import json
from flask_login import current_user
from sqlalchemy import distinct
from app import db

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Google Places API Key
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
if not GOOGLE_MAPS_API_KEY:
    raise EnvironmentError("GOOGLE_MAPS_API_KEY environment variable is not set")

@api_bp.route('/spots/<int:spot_id>', methods=['GET'])
def get_spot(spot_id):
    """スポット詳細情報を取得するAPI"""
    # スポットとそれに関連する写真、アフィリエイトリンク、SNS投稿を一度に取得
    spot = Spot.query.options(
        joinedload(Spot.photos),
        joinedload(Spot.affiliate_links),
        joinedload(Spot.social_posts)
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
        'location': spot.location,
        'category': spot.category,
        'latitude': spot.latitude,
        'longitude': spot.longitude,
        'google_maps_url': google_maps_url,
        'photos': [
            {
                'id': photo.id,
                'photo_url': photo.photo_url
            } for photo in spot.photos
        ],
        'affiliate_links': [
            {
                'id': link.id,
                'platform': link.platform,
                'url': link.url,
                'title': link.title,
                'description': link.description,
                'logo_url': link.logo_url,
                'icon_key': link.icon_key
            } for link in spot.affiliate_links if link.is_active
        ] if hasattr(spot, 'affiliate_links') else [],
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
        'X-Goog-FieldMask': 'displayName,formattedAddress,location,types,photos',
        'X-Goog-LanguageCode': 'ja'  # 日本語を指定
    }
    
    print(f"Calling Google Places API v1 Details with URL: {url}")
    print(f"Headers: {headers}")
    
    try:
        # GETリクエストを使用
        response = requests.get(url, headers=headers)
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
                    if country:
                        summary_parts.append(country)
                    if prefecture:
                        summary_parts.append(prefecture)
                    if locality:
                        summary_parts.append(locality)
                    
                    if summary_parts:
                        place_details['summary_location'] = '、'.join(summary_parts)
        
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
    """Google Places Autocomplete APIを呼び出す"""
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
        'X-Goog-LanguageCode': 'ja'  # 日本語を指定
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
        'X-Goog-FieldMask': 'photos.0.name'  # 最初の写真のみ取得
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
    
    # Google写真参照情報がない場合はエラー
    if not photo.is_google_photo or not photo.google_photo_reference:
        return jsonify({'error': 'No Google photo reference available'}), 404
    
    # 写真参照情報を使用してURLを生成
    photo_reference = photo.google_photo_reference
    photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=800&maxWidthPx=800&key={GOOGLE_MAPS_API_KEY}"
    
    return jsonify({
        'photo_id': photo.id,
        'photo_url': photo_url,
        'is_google_photo': photo.is_google_photo
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
            'is_google_photo': photo.is_google_photo
        }
        
        if photo.is_google_photo and photo.google_photo_reference:
            # Google写真の場合は参照情報を含める
            photo_data['google_photo_reference'] = photo.google_photo_reference
            photo_data['photo_url'] = f"https://places.googleapis.com/v1/{photo.google_photo_reference}/media?maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}"
        else:
            # ユーザーアップロード写真の場合はURLを含める
            photo_data['photo_url'] = photo.photo_url
        
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