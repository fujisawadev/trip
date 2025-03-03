from app import create_app, db
from app.models import Photo
import os
import requests
import time

# Google Maps API Key - 直接指定
GOOGLE_MAPS_API_KEY = "AIzaSyD1eKEJje0XpgVnRXCdeKPDzdZTrnlVjFc"

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

def update_cdn_urls():
    """Google Photo Referenceを持つすべての写真のCDN URLを更新する"""
    app = create_app()
    with app.app_context():
        # Google Photo Referenceを持ち、photo_urlがNULLまたは空の写真を取得
        photos = Photo.query.filter(
            Photo.is_google_photo == True,
            Photo.google_photo_reference.isnot(None),
            (Photo.photo_url.is_(None) | (Photo.photo_url == ''))
        ).all()
        
        print(f"更新対象の写真: {len(photos)}件")
        
        updated_count = 0
        error_count = 0
        
        for i, photo in enumerate(photos):
            print(f"処理中: {i+1}/{len(photos)} - Photo ID: {photo.id}")
            
            # CDN URLを取得
            cdn_url = get_cdn_url_from_reference(photo.google_photo_reference)
            
            if cdn_url:
                # CDN URLを更新
                photo.photo_url = cdn_url
                updated_count += 1
                print(f"  ✓ CDN URL更新成功: {cdn_url[:50]}...")
            else:
                error_count += 1
                print(f"  ✗ CDN URL取得失敗: {photo.google_photo_reference[:30]}...")
            
            # 10件ごとにコミット
            if (i + 1) % 10 == 0:
                db.session.commit()
                print(f"中間コミット完了: {i+1}件")
                # API制限を考慮して少し待機
                time.sleep(1)
        
        # 残りの変更をコミット
        db.session.commit()
        
        print("\n===== 処理完了 =====")
        print(f"更新成功: {updated_count}件")
        print(f"更新失敗: {error_count}件")

if __name__ == "__main__":
    update_cdn_urls() 