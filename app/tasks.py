import os
import json
import uuid
from datetime import datetime
import logging
import requests
import traceback

from app import db
from app.models import ImportProgress, User, Spot, SocialPost, ImportHistory, AffiliateLink
from app.utils.rakuten_api import safe_decode_text
from app.services.google_places import get_place_review_summary

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
    
    def check_if_cancelled():
        """ジョブがキャンセルされているかチェックする"""
        try:
            progress = ImportProgress.query.filter_by(job_id=job_id).first()
            if progress and progress.status == 'cancelled':
                logger.info(f"[Job {job_id}] Job was cancelled by user. Exiting gracefully.")
                raise Exception("CANCELLED_BY_USER")
        except Exception as e:
            if "CANCELLED_BY_USER" in str(e):
                raise
            # DBエラーの場合はログに記録するが処理は続行
            logger.warning(f"[Job {job_id}] Error checking cancellation status: {e}")
    
    # 開始前にキャンセル状態チェック
    check_if_cancelled()
    
    _update_job_status(job_id, 'processing')

    try:
        # ユーザーとトークンを取得
        user = User.query.get(user_id)
        if not (user and user.instagram_token):
            raise ValueError("User not found or Instagram not connected.")

        # --- 1. 全投稿を取得 ---
        check_if_cancelled()  # 投稿取得前にチェック
        
        all_posts = _fetch_all_instagram_posts(job_id, user.instagram_token, start_date_str, end_date_str)
        if not all_posts:
            logger.info(f"[Job {job_id}] No posts found for the specified period.")
            _update_job_status(job_id, 'completed', result_data={'spot_candidates': [], 'analyzed_posts': []})
            return

        # --- 2. 投稿を分析 ---
        check_if_cancelled()  # 分析前にチェック
        
        spot_candidates = _analyze_posts_with_openai(job_id, all_posts)

        # --- 3. Google Places APIで情報を補完 ---
        check_if_cancelled()  # Google Places検索前にチェック
        
        enriched_candidates = _enrich_candidates_with_google_places(job_id, spot_candidates)

        logger.info(f"[Job {job_id}] Found {len(enriched_candidates)} potential spots.")
        
        result = {
            'spot_candidates': enriched_candidates,
            'analyzed_posts': [{'id': p.get('id'), 'permalink': p.get('permalink'), 'timestamp': p.get('timestamp')} for p in all_posts]
        }
        _update_job_status(job_id, 'completed', result_data=result)
        logger.info(f"[Job {job_id}] Processing finished successfully.")

    except Exception as e:
        # キャンセルされた場合は静かに終了
        if "CANCELLED_BY_USER" in str(e):
            logger.info(f"[Job {job_id}] Job was cancelled by user. Exiting gracefully.")
            return
        
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
                # エラーレスポンスの詳細を解析
                try:
                    error_data = json.loads(response.text)
                    error_info = error_data.get('error', {})
                    error_code = error_info.get('code')
                    error_message = error_info.get('message', response.text)
                    
                    if error_code == 190:
                        raise Exception(f"Instagram連携の有効期限が切れています。再度連携してください。 (Code: {error_code})")
                    elif error_code in [4, 17]:
                        raise Exception(f"Instagram APIの利用制限に達しました。時間をおいて再度お試しください。 (Code: {error_code})")
                    else:
                        raise Exception(f"Instagram API error: {error_message} (Code: {error_code})")
                except json.JSONDecodeError:
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
        出力形式をJSON形式で返してください: {{"spots": ["施設名1", "施設名2", ...]}}
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
            # 位置情報名も文字化けチェック
            location_name = safe_decode_text(location['name'])
            if location_name.strip():  # クリーンアップ後に空でない場合のみ追加
                spot_names.insert(0, location_name)
        
        # 重複を削除しつつ、順番を維持
        unique_spot_names = list(dict.fromkeys(spot_names))

        for name in unique_spot_names:
            # 文字化けチェックとクリーンアップ
            cleaned_name = safe_decode_text(name)
            cleaned_caption = safe_decode_text(caption)
            
            spot_candidates.append({
                'name': cleaned_name,
                'instagram_post_id': post.get('id'),
                'instagram_permalink': post.get('permalink'),
                'instagram_caption': cleaned_caption,
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

def _update_save_job_status(save_job_id, status, error_info=None, result_data=None):
    """DB の保存ジョブステータスを更新する"""
    try:
        progress = ImportProgress.query.filter_by(save_job_id=save_job_id).first()
        if progress:
            progress.save_status = status
            if error_info:
                progress.save_error_info = error_info
            if result_data:
                progress.save_result_data = json.dumps(result_data, ensure_ascii=False)
            db.session.commit()
            logger.info(f"[SaveJob {save_job_id}] Status updated to {status}.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[SaveJob {save_job_id}] Failed to update save job status: {e}")

def save_spots_async(save_job_id, user_id, spot_candidates):
    """
    選択されたスポット候補を非同期で保存する
    """
    logger.info(f"[SaveJob {save_job_id}] Save processing started for user {user_id}.")
    
    def check_if_cancelled():
        """保存ジョブがキャンセルされているかチェックする"""
        try:
            progress = ImportProgress.query.filter_by(save_job_id=save_job_id).first()
            if progress and progress.save_status == 'cancelled':
                logger.info(f"[SaveJob {save_job_id}] Save job was cancelled by user. Exiting gracefully.")
                raise Exception("CANCELLED_BY_USER")
        except Exception as e:
            if "CANCELLED_BY_USER" in str(e):
                raise
            # DBエラーの場合はログに記録するが処理は続行
            logger.warning(f"[SaveJob {save_job_id}] Error checking cancellation status: {e}")
    
    # 開始前にキャンセル状態チェック
    check_if_cancelled()
    
    _update_save_job_status(save_job_id, 'processing')
    
    try:
        # ユーザー情報を取得
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found.")
        
        logger.info(f"[SaveJob {save_job_id}] Processing {len(spot_candidates)} spot candidates.")
        
        saved_spots = []
        
        # スポット候補の情報をログに出力
        for i, spot_data in enumerate(spot_candidates):
            # 定期的にキャンセル状態をチェック（5件ごと）
            if i % 5 == 0:
                check_if_cancelled()
            
            logger.info(f"[SaveJob {save_job_id}] Processing spot {i+1}/{len(spot_candidates)}: {spot_data.get('name', 'Unknown')}")
            
            # スポットの基本情報を設定
            spot = Spot(
                user_id=user.id,
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
            
            # Google Placesのtypesから日本語カテゴリを生成
            if 'types' in spot_data and spot_data['types']:
                try:
                    spot.types = json.dumps(spot_data['types'])
                    logger.info(f"[SaveJob {save_job_id}] Types設定: {spot.types}")
                except Exception as e:
                    logger.error(f"[SaveJob {save_job_id}] Types設定エラー: {str(e)}")
                    spot.types = json.dumps([])
                
                # OpenAI APIを使用して日本語カテゴリを生成
                if OPENAI_API_KEY:
                    try:
                        import openai
                        from openai import OpenAI
                        
                        # OpenAIクライアントの初期化
                        client = OpenAI(
                            api_key=OPENAI_API_KEY,
                            timeout=30.0
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
                        
                        JSON形式で日本語カテゴリ名を返してください:
                        """
                        
                        logger.info(f"[SaveJob {save_job_id}] OpenAI APIを呼び出してカテゴリを生成")
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            response_format={"type": "json_object"},
                            messages=[
                                {"role": "system", "content": "あなたはGoogle Placesのタイプ情報から適切な日本語カテゴリを生成する専門家です。"},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=50
                        )
                        
                        category_result = json.loads(response.choices[0].message.content.strip())
                        category = category_result.get('category', 'その他')
                        spot.category = category
                        logger.info(f"[SaveJob {save_job_id}] 生成されたカテゴリ: {category}")
                    except Exception as e:
                        logger.error(f"[SaveJob {save_job_id}] カテゴリ生成エラー: {str(e)}")
                        spot.category = "その他"
            
            # 日本語のsummary_locationを取得
            if spot_data.get('place_id') and (not spot.summary_location or spot.summary_location == ''):
                try:
                    logger.info(f"[SaveJob {save_job_id}] 日本語のsummary_locationを取得: place_id={spot_data.get('place_id')}")
                    
                    # Google Places APIの詳細エンドポイントを呼び出す
                    details_url = f"https://places.googleapis.com/v1/places/{spot_data.get('place_id')}"
                    details_headers = {
                        'Content-Type': 'application/json',
                        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                        'X-Goog-FieldMask': 'addressComponents',
                        'X-Goog-LanguageCode': 'ja',
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
                                logger.info(f"[SaveJob {save_job_id}] 日本語のsummary_locationを設定: {spot.summary_location}")
                    else:
                        logger.warning(f"[SaveJob {save_job_id}] Google Places API詳細取得エラー: ステータスコード {details_response.status_code}")
                except Exception as e:
                    logger.error(f"[SaveJob {save_job_id}] summary_location取得エラー: {str(e)}")
            
            # 日本語のsummary_locationが取得できなかった場合、searchTextエンドポイントを使用
            if spot_data.get('place_id') and (not spot.summary_location or not _is_japanese(spot.summary_location)):
                try:
                    logger.info(f"[SaveJob {save_job_id}] searchTextエンドポイントを使用して日本語情報を取得: {spot.name}")
                    
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
                                    logger.info(f"[SaveJob {save_job_id}] searchTextから日本語のsummary_locationを設定: {spot.summary_location}")
                            
                            # フォーマット済み住所が取得できたら更新
                            if 'formattedAddress' in place and place['formattedAddress'] and not spot.formatted_address:
                                spot.formatted_address = place['formattedAddress']
                                logger.info(f"[SaveJob {save_job_id}] searchTextからformatted_addressを更新: {spot.formatted_address}")
                except Exception as e:
                    logger.error(f"[SaveJob {save_job_id}] searchText API呼び出しエラー: {str(e)}")
            
            # レビュー要約（editorialSummary → reviewSummary 優先、languageCode=ja）を取得
            try:
                if spot.google_place_id and (not getattr(spot, 'review_summary', None) or not spot.review_summary):
                    fetched_summary = get_place_review_summary(spot.google_place_id)
                    if fetched_summary:
                        spot.review_summary = fetched_summary
                        logger.info(f"[SaveJob {save_job_id}] review_summary を設定しました（{len(fetched_summary)} 文字）")
            except Exception as e:
                logger.warning(f"[SaveJob {save_job_id}] review_summary取得エラー（続行）: {str(e)}")

            logger.info(f"[SaveJob {save_job_id}] スポットをデータベースに追加")
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
            logger.info(f"[SaveJob {save_job_id}] スポットID: {spot.id}")
            
            # Instagram投稿との紐付けを追加
            if spot_data.get('instagram_permalink'):
                try:
                    social_post = SocialPost(
                        user_id=user.id,
                        spot_id=spot.id,
                        platform='instagram',
                        post_url=spot_data.get('instagram_permalink')
                    )
                    db.session.add(social_post)
                    logger.info(f"[SaveJob {save_job_id}] Instagram投稿を紐付け: {spot_data.get('instagram_permalink')}")
                except Exception as e:
                    logger.error(f"[SaveJob {save_job_id}] Instagram投稿紐付けエラー: {str(e)}")
            
            # インポート履歴の保存
            if spot_data.get('instagram_post_id'):
                try:
                    import_history = ImportHistory(
                        user_id=user.id,
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
                    logger.info(f"[SaveJob {save_job_id}] インポート履歴を保存: Instagram投稿ID={spot_data.get('instagram_post_id')}")
                except Exception as e:
                    logger.error(f"[SaveJob {save_job_id}] インポート履歴保存エラー: {str(e)}")
            
            # 楽天トラベルアフィリエイトリンクの自動生成（仕様変更のため一時停止）
            # if user.rakuten_affiliate_id and spot.name:
            #     try:
            #         logger.info(f"[SaveJob {save_job_id}] 楽天トラベルAPI検索: {spot.name}")
            #         from app.utils.rakuten_api import search_hotel_with_fallback, select_best_hotel_with_evaluation, generate_rakuten_affiliate_url
            #         hotel_results = search_hotel_with_fallback(spot.name, user.rakuten_affiliate_id)
            #         if hotel_results.get('error') == 'no_hotels_found':
            #             logger.info(f"[SaveJob {save_job_id}] 楽天トラベル: '{spot.name}'に該当するホテルが見つかりませんでした")
            #         elif hotel_results.get('error'):
            #             logger.warning(f"[SaveJob {save_job_id}] 楽天トラベルAPIエラー: {hotel_results.get('message', 'Unknown error')}")
            #         elif 'hotels' in hotel_results and len(hotel_results['hotels']) > 0:
            #             selected_hotel = select_best_hotel_with_evaluation(spot.name, hotel_results)
            #             if selected_hotel:
            #                 if 'hotel' in selected_hotel and len(selected_hotel['hotel']) > 0:
            #                     hotel_info = selected_hotel['hotel'][0]
            #                     if 'hotelBasicInfo' in hotel_info and hotel_info['hotelBasicInfo'].get('hotelInformationUrl'):
            #                         hotel_url = hotel_info['hotelBasicInfo']['hotelInformationUrl']
            #                         affiliate_url = generate_rakuten_affiliate_url(hotel_url, user.rakuten_affiliate_id)
            #                         affiliate_link = AffiliateLink(
            #                             spot_id=spot.id,
            #                             platform='rakuten',
            #                             url=affiliate_url,
            #                             title='楽天トラベル',
            #                             description='楽天トラベルで予約 (PRを含む)',
            #                             icon_key='rakuten-travel',
            #                             is_active=True
            #                         )
            #                         db.session.add(affiliate_link)
            #     except Exception as e:
            #         logger.error(f"[SaveJob {save_job_id}] 楽天トラベルアフィリエイトリンク生成エラー: {str(e)}")
        
        logger.info(f"[SaveJob {save_job_id}] データベースに変更をコミット")
        db.session.commit()
        
        logger.info(f"[SaveJob {save_job_id}] コミット成功: {len(saved_spots)}件のスポットを保存")
        
        result = {
            'count': len(saved_spots),
            'saved_spots': saved_spots
        }
        _update_save_job_status(save_job_id, 'completed', result_data=result)
        logger.info(f"[SaveJob {save_job_id}] Save processing finished successfully.")

    except Exception as e:
        # キャンセルされた場合は静かに終了
        if "CANCELLED_BY_USER" in str(e):
            logger.info(f"[SaveJob {save_job_id}] Save job was cancelled by user. Exiting gracefully.")
            return
        
        logger.error(f"[SaveJob {save_job_id}] An error occurred: {e}")
        logger.error(traceback.format_exc())
        
        # Sentryにエラー詳細を送信
        try:
            import sentry_sdk
            sentry_sdk.set_context("save_job_context", {
                "save_job_id": save_job_id,
                "user_id": user_id,
                "spot_candidates_count": len(spot_candidates) if spot_candidates else 0,
                "function": "save_spots_async"
            })
            sentry_sdk.capture_exception(e)
        except Exception as sentry_error:
            logger.error(f"[SaveJob {save_job_id}] Failed to send error to Sentry: {sentry_error}")
        
        db.session.rollback()
        _update_save_job_status(save_job_id, 'failed', error_info=str(e))

def _is_japanese(text):
    """テキストが日本語かどうかを判定する"""
    if not text:
        return False
    
    import re
    # ひらがな、カタカナ、漢字の範囲
    japanese_pattern = re.compile(r'[ひらがなカタカナ漢字\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+')
    return bool(japanese_pattern.search(text)) 