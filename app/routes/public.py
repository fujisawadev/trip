from flask import Blueprint, render_template, abort, jsonify, redirect, Response, url_for, request
from app.models import User, Spot, Photo, SocialAccount, SocialPost
from app import db
from sqlalchemy.orm import joinedload
import requests
import os
import json
from flask_login import current_user

# 新しいサービスをインポート
from app.services.google_photos import get_google_photos_by_place_id

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
    
    # ユーザーが作成したスポットを取得
    spots = Spot.query.filter_by(user_id=user.id, is_active=True).order_by(Spot.created_at.desc()).all()
    
    # スポットをJSONシリアライズ可能な形式に変換
    spots_data = []
    for spot in spots:
        spots_data.append(spot.to_dict())

    # ソーシャルアカウント情報を取得
    social_accounts = SocialAccount.query.filter_by(user_id=user.id).first()
    
    return render_template('public/new_profile.html', 
                          user=user, 
                          spots=spots_data,
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
    """ユーザーの新しいマップページを表示"""
    # ユーザーをディスプレイ名またはユーザー名で取得
    user = User.query.filter(
        (User.display_name == displayname) | (User.username == displayname)
    ).first_or_404()
    
    # アクティブなスポットを取得
    spots = Spot.query.filter_by(user_id=user.id, is_active=True).all()
    
    # スポットをJSONシリアライズ可能な形式に変換
    spots_data = []
    for spot in spots:
        spot_dict = {
            'id': spot.id,
            'name': spot.name,
            'location': spot.location,
            'latitude': spot.latitude,
            'longitude': spot.longitude,
            'category': spot.category,
            'description': spot.description,
            'user_id': spot.user_id,
            'photos': [{'photo_url': photo.photo_url} for photo in spot.photos] if spot.photos else []
        }
        spots_data.append(spot_dict)
    
    # ソーシャルアカウント情報を取得
    social_accounts = SocialAccount.query.filter_by(user_id=user.id).all()
    
    return render_template('public/new_map.html',
                         user=user,
                         spots=spots_data,
                         social_accounts=social_accounts,
                         config={'GOOGLE_MAPS_API_KEY': GOOGLE_MAPS_API_KEY})

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
    spot = Spot.query.options(joinedload(Spot.affiliate_links)).filter_by(id=spot_id, user_id=user.id, is_active=True).first_or_404()

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
    
    return render_template('public/spot_detail_page.html', 
                          user=user, 
                          spot=spot, 
                          photos=all_photos,
                          social_links=social_links) 