from flask import Blueprint, render_template, abort, jsonify, redirect, Response, url_for
from app.models import User, Spot, Photo, SocialAccount
from app import db
from sqlalchemy.orm import joinedload
import requests
import os
import json

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
    """公開プロフィールページを表示する"""
    user = User.query.get_or_404(user_id)
    
    # ユーザーが作成したスポットを取得
    spots = Spot.query.filter_by(user_id=user_id, is_active=True).all()
    
    # ソーシャルアカウント情報を取得
    social_accounts = SocialAccount.query.filter_by(user_id=user_id).first()
    
    # 写真がないスポットのGoogle Places APIから写真を取得
    google_photos = {}
    for spot in spots:
        # スポットに関連する写真を取得
        photos = Photo.query.filter_by(spot_id=spot.id).all()
        print(f"スポット {spot.id}: 写真数={len(photos)}, google_place_id={spot.google_place_id}")
        
        # Google写真参照情報を持つ写真があるか確認
        google_photo = Photo.query.filter_by(spot_id=spot.id, is_google_photo=True).first()
        
        if google_photo and google_photo.google_photo_reference:
            # 既に保存されているGoogle写真参照情報を使用
            photo_reference = google_photo.google_photo_reference
            photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}"
            google_photos[spot.id] = photo_url
            print(f"保存済み写真参照情報使用: スポットID={spot.id}, 参照={photo_reference}")
        elif not photos and spot.google_place_id:
            # 写真がなく、かつGoogle Place IDがある場合はAPIから取得
            try:
                # Google Places APIを直接呼び出す
                url = f"https://places.googleapis.com/v1/places/{spot.google_place_id}"
                headers = {
                    'Content-Type': 'application/json',
                    'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                    'X-Goog-FieldMask': 'photos.0.name'  # 最初の写真のみ取得
                }
                
                print(f"Google Places API呼び出し: URL={url}")
                print(f"ヘッダー: {headers}")
                
                api_response = requests.get(url, headers=headers)
                print(f"APIレスポンスステータス: {api_response.status_code}")
                
                if api_response.status_code == 200:
                    data = api_response.json()
                    print(f"APIレスポンスデータ: {data}")
                    
                    if 'photos' in data and len(data['photos']) > 0:
                        photo = data['photos'][0]
                        photo_reference = photo.get('name', '')
                        if photo_reference:
                            # 新しいPhotos APIのエンドポイントを使用
                            photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}"
                            google_photos[spot.id] = photo_url
                            print(f"写真URL取得成功: スポットID={spot.id}, URL={photo_url}")
                            
                            # 写真参照情報をデータベースに保存（将来の使用のため）
                            new_photo = Photo(
                                spot_id=spot.id,
                                photo_url=None,
                                google_photo_reference=photo_reference,
                                is_google_photo=True
                            )
                            db.session.add(new_photo)
                            db.session.commit()
                    else:
                        print(f"写真が見つかりませんでした: スポットID={spot.id}")
                else:
                    print(f"APIエラー: スポットID={spot.id}, ステータス={api_response.status_code}")
                    if hasattr(api_response, 'text'):
                        print(f"エラーレスポンス: {api_response.text}")
            except Exception as e:
                print(f"例外発生: スポットID={spot.id}, エラー={str(e)}")
    
    print(f"取得した写真: {google_photos}")
    
    return render_template('public/profile.html', 
                          user=user, 
                          spots=spots,
                          social_accounts=social_accounts,
                          google_photos=google_photos,
                          config={'GOOGLE_MAPS_API_KEY': GOOGLE_MAPS_API_KEY})

@public_bp.route('/spot/<int:spot_id>')
def spot_detail(spot_id):
    """スポット詳細ページを表示する"""
    # スポットとそれに関連する写真を一度に取得
    spot = Spot.query.options(joinedload(Spot.user)).get_or_404(spot_id)
    
    # 非公開のスポットの場合は404を返す
    if not spot.is_active:
        abort(404)
    
    # スポットに関連する写真を取得
    photos = Photo.query.filter_by(spot_id=spot_id).all()
    print(f"スポット詳細 {spot_id}: 写真数={len(photos)}, google_place_id={spot.google_place_id}")
    
    # Google Places APIから写真を取得するかどうか
    google_photo_url = None
    
    # Google写真参照情報を持つ写真があるか確認
    google_photo = Photo.query.filter_by(spot_id=spot_id, is_google_photo=True).first()
    
    if google_photo and google_photo.google_photo_reference:
        # 既に保存されているGoogle写真参照情報を使用
        photo_reference = google_photo.google_photo_reference
        google_photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=800&maxWidthPx=800&key={GOOGLE_MAPS_API_KEY}"
        print(f"スポット詳細 - 保存済み写真参照情報使用: 参照={photo_reference}")
    elif not photos and spot.google_place_id:
        # 写真がない場合はGoogle Places APIから取得
        try:
            # Google Places APIを直接呼び出す
            url = f"https://places.googleapis.com/v1/places/{spot.google_place_id}"
            headers = {
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                'X-Goog-FieldMask': 'photos.0.name'  # 最初の写真のみ取得
            }
            
            print(f"スポット詳細 - Google Places API呼び出し: URL={url}")
            print(f"スポット詳細 - ヘッダー: {headers}")
            
            api_response = requests.get(url, headers=headers)
            print(f"スポット詳細 - APIレスポンスステータス: {api_response.status_code}")
            
            if api_response.status_code == 200:
                data = api_response.json()
                print(f"スポット詳細 - APIレスポンスデータ: {data}")
                
                if 'photos' in data and len(data['photos']) > 0:
                    photo = data['photos'][0]
                    photo_reference = photo.get('name', '')
                    if photo_reference:
                        # 新しいPhotos APIのエンドポイントを使用
                        google_photo_url = f"https://places.googleapis.com/v1/{photo_reference}/media?maxHeightPx=800&maxWidthPx=800&key={GOOGLE_MAPS_API_KEY}"
                        print(f"スポット詳細 - 写真URL取得成功: URL={google_photo_url}")
                        
                        # 写真参照情報をデータベースに保存（将来の使用のため）
                        new_photo = Photo(
                            spot_id=spot_id,
                            photo_url=None,
                            google_photo_reference=photo_reference,
                            is_google_photo=True
                        )
                        db.session.add(new_photo)
                        db.session.commit()
                else:
                    print(f"スポット詳細 - 写真が見つかりませんでした")
            else:
                print(f"スポット詳細 - APIエラー: ステータス={api_response.status_code}")
                if hasattr(api_response, 'text'):
                    print(f"スポット詳細 - エラーレスポンス: {api_response.text}")
        except Exception as e:
            print(f"スポット詳細 - 例外発生: エラー={str(e)}")
    
    return render_template('public/spot_detail.html', 
                          spot=spot,
                          photos=photos,
                          google_photo_url=google_photo_url)

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
        "google_place_id": spot.google_place_id,
        "google_photo_reference": spot.google_photo_reference
    }
    
    # 関連する写真を取得
    photos = Photo.query.filter_by(spot_id=spot.id).all()
    photo_info = []
    for photo in photos:
        photo_info.append({
            "photo_id": photo.id,
            "photo_url": photo.photo_url,
            "is_google_photo": photo.is_google_photo,
            "google_photo_reference": photo.google_photo_reference
        })
    
    spot_info["photos"] = photo_info
    
    # Google Photo Referenceが有効な場合、CDN URLを取得
    cdn_url = None
    cdn_accessible = False
    
    if spot.google_photo_reference and spot.google_photo_reference != 'null' and spot.google_photo_reference != 'None':
        url = f"https://places.googleapis.com/v1/{spot.google_photo_reference}/media?skipHttpRedirect=true&maxHeightPx=400&maxWidthPx=400&key={GOOGLE_MAPS_API_KEY}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'photoUri' in data:
                        cdn_url = data['photoUri']
                        # CDN URLにアクセス可能かチェック
                        cdn_check = requests.head(cdn_url)
                        cdn_accessible = cdn_check.status_code == 200
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            spot_info["error"] = str(e)
    
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
            <p>{spot.google_photo_reference or 'None'}</p>
            
            <h2>CDN URL</h2>
            <p>{cdn_url or 'None'}</p>
            
            <h2>画像テスト</h2>
            <div>
                <h3>1. プロキシエンドポイント経由</h3>
                <img src="{url_for('public.photo_proxy', photo_reference=spot.google_photo_reference) if spot.google_photo_reference and spot.google_photo_reference != 'null' and spot.google_photo_reference != 'None' else url_for('static', filename='default_profile.jpg')}" alt="甲子園 via Proxy">
                
                <h3>2. CDN URL直接アクセス（取得できた場合）</h3>
                {f'<img src="{cdn_url}" alt="甲子園 via CDN">' if cdn_url else '<p>CDN URLが取得できませんでした</p>'}
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
    
    # photo_referenceが無効な場合はデフォルト画像にリダイレクト
    if not photo_reference or photo_reference == 'null' or photo_reference == 'None':
        return redirect(url_for('static', filename='default_profile.jpg'))
    
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
    
    # すべての方法が失敗した場合、デフォルト画像にリダイレクト
    return redirect(url_for('static', filename='default_profile.jpg')) 