import os
import json
import requests
import logging
from flask import jsonify, request, abort, Blueprint
from app.models import Spot, Photo, AffiliateLink, SocialPost, ImportHistory, ImportProgress
from sqlalchemy.orm import joinedload
from flask_login import current_user
from sqlalchemy import distinct
from app import db
import re
from datetime import datetime
from app.utils.instagram_helpers import extract_cursor_from_url
# 楽天APIのユーティリティ関数をインポート
from app.utils.rakuten_api import search_hotel, similar_text, generate_rakuten_affiliate_url

# API用のブループリントを直接作成
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Google Places API Key
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
if not GOOGLE_MAPS_API_KEY:
    raise EnvironmentError("GOOGLE_MAPS_API_KEY environment variable is not set")

# OpenAI API Key
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY environment variable is not set. AI features will not work.")

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
        'X-Goog-LanguageCode': 'ja',  # 日本語を指定
        'User-Agent': 'my-map.link App (https://my-map.link)'
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
            return jsonify({'error': f'Instagram API error: {response.text}'}), 400
        
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
            以下のInstagramの投稿キャプションから、訪問した場所やスポットの名前を全て抽出してください。
            複数の場所が言及されている場合は、それぞれを別々に抽出してください。
            最大5つまでのスポットを抽出し、JSONリスト形式で返してください。
            
            キャプション: {caption}
            
            出力形式:
            {{
              "spots": [
                "スポット名1",
                "スポット名2",
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
                location=spot_data.get('formatted_address', ''),
                latitude=spot_data.get('latitude'),
                longitude=spot_data.get('longitude'),
                category=spot_data.get('types', [])[0] if spot_data.get('types') else None,
                google_place_id=spot_data.get('place_id'),
                formatted_address=spot_data.get('formatted_address', ''),
                summary_location=spot_data.get('summary_location', ''),
                google_photo_reference=spot_data.get('photo_reference', ''),
                thumbnail_url=spot_data.get('thumbnail_url', ''),
                is_active=False  # 非公開状態で保存
            )
            
            print(f"スポットモデル作成: {spot.name}, user_id={spot.user_id}")
            print(f"  - formatted_address: {spot.formatted_address}")
            print(f"  - google_photo_reference: {spot.google_photo_reference}")
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
            
            print(f"スポットをデータベースに追加")
            saved_spots.append({
                'name': spot.name,
                'category': spot.category,
                'formatted_address': spot.formatted_address,
                'types': spot.types,
                'summary_location': spot.summary_location,
                'google_photo_reference': spot.google_photo_reference
            })
            db.session.add(spot)
            db.session.flush()  # IDを取得するためのフラッシュ
            print(f"スポットID: {spot.id}")
            
            # Google Place IDがあれば、写真を取得・保存
            if spot_data.get('place_id'):
                try:
                    print(f"写真を取得: place_id={spot_data.get('place_id')}")
                    
                    # Google Places APIを呼び出して写真情報を取得
                    url = f"https://places.googleapis.com/v1/places/{spot_data.get('place_id')}"
                    headers = {
                        'Content-Type': 'application/json',
                        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                        'X-Goog-FieldMask': 'photos'  # すべての写真の情報を取得
                    }
                    
                    api_response = requests.get(url, headers=headers)
                    
                    if api_response.status_code == 200:
                        place_data = api_response.json()
                        photos = place_data.get('photos', [])
                        
                        if photos and len(photos) > 0:
                            # 最大5枚の写真を保存
                            for i, photo in enumerate(photos[:5]):
                                photo_name = photo.get('name')
                                if photo_name:
                                    # 写真URLを生成
                                    photo_url = f"https://places.googleapis.com/v1/{photo_name}/media?key={GOOGLE_MAPS_API_KEY}&maxHeightPx=800&maxWidthPx=800"
                                    
                                    # 写真情報を保存
                                    photo = Photo(
                                        spot_id=spot.id,
                                        photo_url=photo_url,
                                        google_photo_reference=photo_name,
                                        is_google_photo=True,
                                        is_primary=(i == 0)  # 最初の写真をプライマリに設定
                                    )
                                    db.session.add(photo)
                                    print(f"写真を追加: photo_name={photo_name}")
                    else:
                        print(f"写真情報の取得に失敗: status_code={api_response.status_code}")
                        print(f"エラーレスポンス: {api_response.text}")
                        
                except Exception as photo_error:
                    print(f"写真の取得・保存エラー: {str(photo_error)}")
                    # 写真の取得に失敗しても処理を続行
            
            # 楽天トラベルアフィリエイトリンクの自動生成
            if current_user.rakuten_affiliate_id and spot.name:
                try:
                    print(f"楽天トラベルAPI検索: {spot.name}")
                    # 楽天トラベルAPIを呼び出してホテル情報を取得
                    hotel_results = search_hotel(spot.name, current_user.rakuten_affiliate_id)
                    
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
                                    
                                    # ホテル名が一致または類似していれば、アフィリエイトリンクを作成
                                    similarity = similar_text(spot.name, hotel_name, min_similarity=0.5)
                                    print(f"類似度チェック: '{spot.name}' と '{hotel_name}' の類似度: {similarity}")
                                    
                                    if similarity:
                                        print(f"類似と判定: {hotel_name}")
                                        
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
                                            
                                            print(f"楽天トラベルアフィリエイトリンクを自動生成: スポット名={spot.name}")
                                            break  # 最初の一致したホテルのみ使用
                except Exception as e:
                    print(f"楽天トラベルアフィリエイトリンク生成エラー: {str(e)}")
        
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