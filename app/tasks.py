import os
import json
import uuid
from datetime import datetime
import logging
import requests
import traceback

from app import db
from app.models import ImportProgress, User

# ロガーの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定数
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
INSTAGRAM_API_VERSION = "v22.0"

def _update_job_status(job_id, status, error_info=None, result_data=None):
    """DBのジョブステータスを更新する"""
    try:
        progress = ImportProgress.query.filter_by(job_id=job_id).first()
        if progress:
            progress.status = status
            if error_info:
                progress.error_info = error_info
            if result_data:
                progress.result_data = json.dumps(result_data, ensure_ascii=False)
            db.session.commit()
            logger.info(f"[Job {job_id}] Status updated to {status}.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[Job {job_id}] Failed to update job status: {e}")

def fetch_and_analyze_posts(job_id, user_id, start_date_str, end_date_str):
    """
    Instagramの投稿を取得し、分析してスポット候補を抽出する非同期タスク。
    """
    logger.info(f"[Job {job_id}] Processing started for user {user_id}.")
    _update_job_status(job_id, 'processing')

    try:
        # ユーザーとトークンを取得
        user = User.query.get(user_id)
        if not (user and user.instagram_token):
            raise ValueError("User not found or Instagram not connected.")

        # --- 1. 全投稿を取得 ---
        all_posts = _fetch_all_instagram_posts(job_id, user.instagram_token, start_date_str, end_date_str)
        if not all_posts:
            logger.info(f"[Job {job_id}] No posts found for the specified period.")
            _update_job_status(job_id, 'completed', result_data={'spot_candidates': [], 'analyzed_posts': []})
            return

        # --- 2. 投稿を分析 ---
        spot_candidates = _analyze_posts_with_openai(job_id, all_posts)

        # --- 3. Google Places APIで情報を補完 ---
        enriched_candidates = _enrich_candidates_with_google_places(job_id, spot_candidates)

        logger.info(f"[Job {job_id}] Found {len(enriched_candidates)} potential spots.")
        
        result = {
            'spot_candidates': enriched_candidates,
            'analyzed_posts': [{'id': p.get('id'), 'permalink': p.get('permalink'), 'timestamp': p.get('timestamp')} for p in all_posts]
        }
        _update_job_status(job_id, 'completed', result_data=result)
        logger.info(f"[Job {job_id}] Processing finished successfully.")

    except Exception as e:
        logger.error(f"[Job {job_id}] An error occurred: {e}")
        logger.error(traceback.format_exc())
        
        # Sentryにエラー詳細を送信
        try:
            import sentry_sdk
            sentry_sdk.set_context("job_context", {
                "job_id": job_id,
                "user_id": user_id,
                "start_date": start_date_str,
                "end_date": end_date_str,
                "function": "fetch_and_analyze_posts"
            })
            sentry_sdk.capture_exception(e)
        except Exception as sentry_error:
            logger.error(f"[Job {job_id}] Failed to send error to Sentry: {sentry_error}")
        
        _update_job_status(job_id, 'failed', error_info=str(e))

def _fetch_all_instagram_posts(job_id, token, start_date_str, end_date_str):
    """指定期間のInstagram投稿をすべて取得する"""
    all_posts = []
    
    start_dt = datetime.fromisoformat(f"{start_date_str}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date_str}T23:59:59+00:00")

    params = {
        "fields": "id,caption,media_type,media_url,permalink,timestamp,location",
        "access_token": token,
        "limit": 50
    }
    url = f"https://graph.instagram.com/{INSTAGRAM_API_VERSION}/me/media"

    is_dev_mode = os.environ.get("FLASK_ENV") == "development"

    while url:
        if is_dev_mode:
            logger.info(f"--- [Job {job_id}] RUNNING IN DEV MODE: LOADING MOCK INSTAGRAM DATA ---")
            with open("tests/mock_data/instagram_posts.json") as f:
                data = json.load(f)
            url = None # 開発モードでは1回でループを抜ける
        else:
            response = requests.get(url, params=params)
            if response.status_code != 200:
                raise Exception(f"Instagram API error: {response.text}")
            data = response.json()
            url = data.get("paging", {}).get("next")
            # 次のリクエストではparamsをリセット
            params = {}

        posts_data = data.get('data', [])
        
        # 期間でフィルタリング
        for post in posts_data:
            post_dt = datetime.fromisoformat(post['timestamp'].replace('Z', '+00:00'))
            if start_dt <= post_dt <= end_dt:
                all_posts.append(post)
        
        # 取得した最も古い投稿が開始日より前なら、ループを抜ける
        if posts_data:
            oldest_post_dt = datetime.fromisoformat(posts_data[-1]['timestamp'].replace('Z', '+00:00'))
            if oldest_post_dt < start_dt:
                break

    logger.info(f"[Job {job_id}] Fetched a total of {len(all_posts)} posts.")
    return all_posts

def _analyze_posts_with_openai(job_id, posts):
    """OpenAI APIを使って投稿からスポット候補を抽出する"""
    if not OPENAI_API_KEY:
        raise ValueError("OpenAI API key not configured.")
    
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=60.0) # タイムアウトを60秒に延長
    
    spot_candidates = []
    
    for post in posts:
        caption = post.get('caption', '')
        if not caption:
            continue
        
        if len(caption) > 1500: # 文字数制限を少し緩和
            caption = caption[:1500]

        prompt = f"""
        以下のInstagramの投稿キャプションから、訪問した場所や店舗、スポットの名前を全て抽出してください。
        複数の場所が言及されている場合は、それぞれを別々に抽出してください。
        最大5つまでのスポットを抽出し、JSONリスト形式で返してください。
        キャプション: {caption}
        出力形式: {{"spots": ["スポット名1", "スポット名2", ...]}}
        """
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "あなたはInstagramの投稿からスポット情報を抽出する専門家です。日本語のキャプションから場所名を正確に抽出してください。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            content = response.choices[0].message.content
            result = json.loads(content)
            spot_names = result.get("spots", [])

        except Exception as e:
            logger.error(f"[Job {job_id}] OpenAI API error for post {post.get('id')}: {e}")
            
            # Sentryに詳細情報を送信
            try:
                import sentry_sdk
                sentry_sdk.set_context("openai_context", {
                    "job_id": job_id,
                    "post_id": post.get('id'),
                    "caption_length": len(caption),
                    "function": "_analyze_posts_with_openai"
                })
                sentry_sdk.capture_exception(e)
            except Exception as sentry_error:
                logger.error(f"[Job {job_id}] Failed to send OpenAI error to Sentry: {sentry_error}")
            
            spot_names = [] # エラー時はAIからの抽出は無しとする

        # Instagramの位置情報があれば最優先で追加
        location = post.get('location')
        if location and 'name' in location and location['name']:
            spot_names.insert(0, location['name'])
        
        # 重複を削除しつつ、順番を維持
        unique_spot_names = list(dict.fromkeys(spot_names))

        for name in unique_spot_names:
            spot_candidates.append({
                'name': name,
                'instagram_post_id': post.get('id'),
                'instagram_permalink': post.get('permalink'),
                'instagram_caption': caption,
                'timestamp': post.get('timestamp')
            })

    logger.info(f"[Job {job_id}] Analysis complete. Found {len(spot_candidates)} candidates.")
    return spot_candidates


def _enrich_candidates_with_google_places(job_id, candidates):
    """Google Places APIで情報を補完する"""
    if not GOOGLE_MAPS_API_KEY:
        logger.warning(f"[Job {job_id}] Google Maps API key not configured. Skipping enrichment.")
        return candidates

    enriched_candidates = []
    for candidate in candidates:
        try:
            # Google Places API v1 (searchText) を使用
            search_url = "https://places.googleapis.com/v1/places:searchText"
            headers = {
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.location,places.types,places.id,places.addressComponents',
                'X-Goog-LanguageCode': 'ja',
                'User-Agent': 'my-map.link App (https://my-map.link)'
            }
            search_data = {
                "textQuery": candidate['name'],
                "languageCode": "ja",
                "regionCode": "JP"
            }
            
            logger.info(f"[Job {job_id}] Searching Google Places for: '{candidate['name']}'")
            response = requests.post(search_url, headers=headers, json=search_data, timeout=10)
            
            # APIレスポンスのステータスコードをチェック
            if response.status_code != 200:
                logger.error(f"[Job {job_id}] Google Places API returned status {response.status_code} for '{candidate['name']}'. Response: {response.text}")
                continue # エラーの場合はこの候補をスキップ

            response_data = response.json()
            logger.info(f"[Job {job_id}] Google Places API response for '{candidate['name']}': {response_data}")
            
            results = response_data.get('places', [])

            if results:
                place = results[0] # 最も関連性の高い結果を使用
                
                # 更新: candidate辞書を直接更新する（フィールドマッピング修正）
                candidate['formatted_address'] = place.get('formattedAddress')
                loc = place.get('location', {})
                candidate['latitude'] = loc.get('latitude')  # 修正: lat → latitude
                candidate['longitude'] = loc.get('longitude')  # 修正: lng → longitude
                candidate['place_id'] = place.get('id')
                candidate['types'] = place.get('types', [])
                candidate['name'] = place.get('displayName', {}).get('text', candidate['name'])
                
                # summary_locationを生成
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
                        candidate['summary_location'] = '、'.join(summary_parts)
                        logger.info(f"[Job {job_id}] - Summary Location: {candidate['summary_location']}")
                    else:
                        candidate['summary_location'] = ''
                else:
                    candidate['summary_location'] = ''
                
                logger.info(f"[Job {job_id}] Successfully enriched '{candidate['name']}' with Google Places data")
                logger.info(f"[Job {job_id}] - Place ID: {candidate['place_id']}")
                logger.info(f"[Job {job_id}] - Coordinates: {candidate['latitude']}, {candidate['longitude']}")
                logger.info(f"[Job {job_id}] - Address: {candidate['formatted_address']}")
                
                # 候補が見つかったものだけをリストに追加
                enriched_candidates.append(candidate)
            else:
                # Googleで見つからなかった候補は一旦除外する
                logger.info(f"[Job {job_id}] Spot '{candidate['name']}' not found on Google Places. Skipping.")

        except Exception as e:
            logger.error(f"[Job {job_id}] Google Places API error for '{candidate['name']}': {e}")
            
            # Sentryに詳細情報を送信
            try:
                import sentry_sdk
                sentry_sdk.set_context("google_places_context", {
                    "job_id": job_id,
                    "candidate_name": candidate['name'],
                    "function": "_enrich_candidates_with_google_places"
                })
                sentry_sdk.capture_exception(e)
            except Exception as sentry_error:
                logger.error(f"[Job {job_id}] Failed to send Google Places error to Sentry: {sentry_error}")
            
            continue # エラーが発生した候補はスキップ

    logger.info(f"[Job {job_id}] Enrichment complete. {len(enriched_candidates)} candidates were enriched.")
    return enriched_candidates 