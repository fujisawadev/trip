import requests
import json
import redis
from flask import current_app

# Redisクライアントのセットアップ
# Flaskアプリケーションのコンテキスト外で直接URLを使う
# configから直接読み込むのではなく、アプリケーションコンテキストを通じて取得する
def get_redis_client():
    redis_url = current_app.config.get('REDIS_URL')
    if not redis_url:
        print("エラー: REDIS_URLが設定されていません。")
        return None
    return redis.from_url(redis_url)

def get_google_photos_by_place_id(place_id: str, max_photos: int = 5) -> list[str]:
    """
    Google Place IDを使用して、場所に関連する写真のURLリストを取得します。
    結果は24時間キャッシュされます。
    """
    if not place_id:
        return []

    # Redisクライアントを取得
    redis_client = get_redis_client()
    if not redis_client:
        return _fetch_photos_from_google(place_id, max_photos) # Redisがない場合は直接取得

    cache_key = f"google_photos:{place_id}"
    
    try:
        # 1. キャッシュを確認
        cached_data = redis_client.get(cache_key)
        if cached_data:
            # キャッシュヒット！JSON文字列をリストに戻して返す
            print(f"キャッシュヒット: {cache_key}")
            return json.loads(cached_data)
        
        # 2. キャッシュがなければ、Googleから取得
        print(f"キャッシュミス: {cache_key}")
        photo_urls = _fetch_photos_from_google(place_id, max_photos)
        
        # 3. 取得結果をキャッシュに保存（有効期限: 24時間 = 86400秒）
        # 結果が空でもキャッシュし、無駄なAPI呼び出しを防ぐ
        redis_client.setex(cache_key, 86400, json.dumps(photo_urls))
        
        return photo_urls

    except redis.exceptions.RedisError as e:
        print(f"Redisエラーが発生しました: {e}。Googleから直接取得します。")
        # Redisに問題がある場合は、直接Googleから取得してフォールバック
        return _fetch_photos_from_google(place_id, max_photos)

def _fetch_photos_from_google(place_id: str, max_photos: int) -> list[str]:
    """
    Google Places APIから直接写真URLを取得する内部関数。
    """
    api_key = current_app.config.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        print("エラー: GOOGLE_MAPS_API_KEYが設定されていません。")
        return []

    place_details_url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': api_key,
        'X-Goog-FieldMask': 'photos'
    }

    try:
        response = requests.get(place_details_url, headers=headers, timeout=5)
        response.raise_for_status()
        place_data = response.json()

        if 'photos' not in place_data or not place_data['photos']:
            return []

        photo_references = [photo['name'] for photo in place_data['photos']]
        
        photo_urls = []
        for ref in photo_references[:max_photos]:
            photo_url = f"https://places.googleapis.com/v1/{ref}/media?key={api_key}&maxHeightPx=800"
            photo_urls.append(photo_url)
        
        return photo_urls

    except requests.exceptions.RequestException as e:
        print(f"Google Places APIへのリクエスト中にエラーが発生しました: {e}")
        return []
    except KeyError as e:
        print(f"APIレスポンスの解析中にエラーが発生しました: {e}")
        return []
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
        return [] 