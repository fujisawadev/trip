"""
改良版スポットDB検索ツール - 自動情報統合対応
"""
import logging
import requests
import os
from langchain.tools import tool
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.models import Spot, User
from app import db

logger = logging.getLogger(__name__)

def _safe_float_conversion(value) -> float:
    """座標値を安全にfloatに変換する"""
    try:
        if value is None:
            return None
        
        # 文字列の場合の処理
        if isinstance(value, str):
            value = value.strip()
            if value.lower() in ['', 'none', 'null', 'nan']:
                return None
        
        # 数値変換を試行
        float_value = float(value)
        
        # NaNや無限大のチェック
        if not (float_value == float_value):  # NaNチェック
            return None
        if float_value == float('inf') or float_value == float('-inf'):
            return None
            
        return float_value
        
    except (ValueError, TypeError, OverflowError) as e:
        logger.warning(f"Failed to convert coordinate value '{value}' to float: {e}")
        return None

def _get_google_place_details(place_id: str) -> dict:
    """Google Places APIから詳細情報を取得"""
    api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    if not api_key or not place_id:
        return {}
    
    try:
        url = f"https://places.googleapis.com/v1/places/{place_id}"
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': api_key,
            'X-Goog-FieldMask': 'displayName,formattedAddress,location,types,photos,rating,userRatingCount,priceLevel,currentOpeningHours,regularOpeningHours,businessStatus,accessibilityOptions',
            'X-Goog-LanguageCode': 'ja'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            logger.debug(f"Google Places API error for {place_id}: {response.status_code}")
            return {}
    except Exception as e:
        logger.debug(f"Google Places API request failed for {place_id}: {e}")
        return {}

def _format_opening_hours(opening_hours_data: dict) -> str:
    """営業時間情報を読みやすい形式にフォーマット"""
    if not opening_hours_data:
        return "営業時間不明"
    
    try:
        if 'weekdayDescriptions' in opening_hours_data:
            # 日本語の営業時間説明を取得
            descriptions = opening_hours_data['weekdayDescriptions']
            if descriptions:
                # 今日と明日の営業時間を抜粋
                today_tomorrow = descriptions[:2]  # 通常は月曜から順番
                return "、".join(today_tomorrow)
        
        # フォールバック: periods情報から生成
        if 'periods' in opening_hours_data:
            periods = opening_hours_data['periods']
            if periods:
                first_period = periods[0]
                open_time = first_period.get('open', {}).get('time', '')
                close_time = first_period.get('close', {}).get('time', '')
                if open_time and close_time:
                    return f"{open_time[:2]}:{open_time[2:]}～{close_time[:2]}:{close_time[2:]}"
        
        return "営業時間要確認"
    except Exception as e:
        logger.debug(f"Opening hours formatting error: {e}")
        return "営業時間要確認"

def _auto_enrich_spot_info(spot: Spot) -> dict:
    """スポット情報を自動的に複数ソースで強化"""
    try:
        # 基本情報
        enriched = {
        "id": spot.id,
        "name": spot.name,
            "description": spot.description or "",
            "category": spot.category or "",
            "location": spot.summary_location or spot.location or spot.formatted_address,
            "detail_url": f"/{getattr(spot.user, 'slug', None) or getattr(spot.user, 'username', 'unknown')}/{spot.id}" if spot.user else f"/unknown/{spot.id}",
            "creator_name": getattr(spot.user, 'slug', None) or getattr(spot.user, 'username', 'unknown') if spot.user else "unknown",
            "created_at": spot.created_at.isoformat() if spot.created_at else None,
            "coordinates": {
                "lat": _safe_float_conversion(spot.latitude),
                "lng": _safe_float_conversion(spot.longitude)
            }
        }
        
        # 写真情報（既存）
        photos = []
        for photo in spot.photos[:3]:
            if photo.photo_url:
                photos.append({
                    'url': photo.photo_url,
                    'alt': getattr(photo, 'alt_text', None) or spot.name
                })
        enriched["photos"] = photos
        
        # Google Places APIからの詳細情報統合
        if spot.google_place_id:
            place_details = _get_google_place_details(spot.google_place_id)
            
            if place_details:
                # 評価情報
                if 'rating' in place_details:
                    enriched['rating'] = _safe_float_conversion(place_details['rating'])
                if 'userRatingCount' in place_details:
                    enriched['review_count'] = place_details['userRatingCount']
                
                # 営業時間情報
                current_hours = place_details.get('currentOpeningHours', {})
                regular_hours = place_details.get('regularOpeningHours', {})
                
                if current_hours:
                    enriched['opening_hours'] = _format_opening_hours(current_hours)
                    enriched['is_open_now'] = current_hours.get('openNow', None)
                elif regular_hours:
                    enriched['opening_hours'] = _format_opening_hours(regular_hours)
                
                # 価格レベル
                if 'priceLevel' in place_details:
                    price_level = place_details['priceLevel']
                    price_labels = {
                        'PRICE_LEVEL_FREE': '無料',
                        'PRICE_LEVEL_INEXPENSIVE': 'リーズナブル',
                        'PRICE_LEVEL_MODERATE': '普通',
                        'PRICE_LEVEL_EXPENSIVE': '高め',
                        'PRICE_LEVEL_VERY_EXPENSIVE': '高級'
                    }
                    enriched['price_level'] = price_labels.get(price_level, '価格不明')
                
                # 営業状況
                if 'businessStatus' in place_details:
                    status = place_details['businessStatus']
                    if status == 'CLOSED_TEMPORARILY':
                        enriched['business_notice'] = '⚠️ 一時休業中の可能性があります'
                    elif status == 'CLOSED_PERMANENTLY':
                        enriched['business_notice'] = '⚠️ 閉業している可能性があります'
                
                # アクセシビリティ情報
                accessibility = place_details.get('accessibilityOptions', {})
                if accessibility.get('wheelchairAccessibleEntrance'):
                    enriched['accessibility'] = 'バリアフリー対応'
        
        # 既存の評価情報（DB）をフォールバックとして使用
        if 'rating' not in enriched and spot.rating:
            enriched['rating'] = _safe_float_conversion(spot.rating)
        if 'review_count' not in enriched and spot.review_count:
            enriched['review_count'] = spot.review_count
        
        return enriched
        
    except Exception as e:
        logger.error(f"Error enriching spot {spot.id}: {e}")
        # エラー時は基本情報のみ返す
        return {
            "id": spot.id,
            "name": spot.name or "不明",
            "description": spot.description or "",
            "location": "不明",
            "detail_url": f"/{spot.user_id}/{spot.id}",
            "photos": [],
            "creator_name": "不明"
        }

@tool
def search_creator_spots(area: str = None, category: str = None, keywords: str = None, user_id: int = None) -> str:
    """
    クリエイターが投稿したスポットをデータベースから検索し、自動的に詳細情報を統合します。
    営業時間、評価、価格レベル、アクセシビリティ等の最新情報を含む包括的な情報を提供します。

    :param area: (任意) 検索したいエリア（例: "東京", "大阪", "渋谷"）
    :param category: (任意) 検索したいカテゴリ（例: "カフェ", "レストラン", "観光名所"）。ユーザーからの指定がない場合は使用しないでください。
    :param keywords: (任意) 検索したい自由なキーワード（例: "インスタ映え", "夜景"）
    :param user_id: (任意) 特定のクリエイターのスポットに限定する場合のユーザーID
    :return: 発見されたスポット情報の詳細な文字列（営業時間、評価等を含む）
    """
    try:
        # クエリ構築（JOINを使ってユーザー情報も取得）
        query = Spot.query.filter_by(is_active=True).options(
            joinedload(Spot.photos),
            joinedload(Spot.user)
        )

        if user_id:
            query = query.filter(Spot.user_id == user_id)

        if area:
            # summary_location, location, formatted_addressの全てを検索対象とする
            area_filter = or_(
                Spot.summary_location.ilike(f"%{area}%"),
                Spot.location.ilike(f"%{area}%"),
                Spot.formatted_address.ilike(f"%{area}%")
            )
            query = query.filter(area_filter)

        if category:
            query = query.filter(Spot.category.ilike(f"%{category}%"))

        if keywords:
            # name, description, categoryの全てを検索対象とする
            keyword_filter = or_(
                Spot.name.ilike(f"%{keywords}%"),
                Spot.description.ilike(f"%{keywords}%"),
                Spot.category.ilike(f"%{keywords}%")
            )
            query = query.filter(keyword_filter)

        # 検索結果を最大10件に制限し、最新順でソート
        spots = query.order_by(Spot.created_at.desc()).limit(10).all()

        if not spots:
            search_info = []
            if area:
                search_info.append(f"エリア: {area}")
            if category:
                search_info.append(f"カテゴリ: {category}")
            if keywords:
                search_info.append(f"キーワード: {keywords}")
            
            return f"検索条件（{', '.join(search_info)}）に合うスポットは見つかりませんでした。"

        # スポット情報を自動的に詳細情報で強化
        results = []
        for spot in spots:
            enriched_spot = _auto_enrich_spot_info(spot)
            
            # LLMが体験設計しやすい構造化された形式で情報を提供
            spot_info = f"""
【スポット情報】{enriched_spot['name']}
・場所: {enriched_spot['location']}
・クリエイター: {enriched_spot['creator_name']}さん
・詳細URL: {enriched_spot['detail_url']}
"""
            
            # 営業・アクセス情報（体験計画に重要）
            operational_info = []
            if enriched_spot.get('opening_hours'):
                operational_info.append(f"営業時間: {enriched_spot['opening_hours']}")
                if enriched_spot.get('is_open_now') is not None:
                    status = "現在営業中" if enriched_spot['is_open_now'] else "現在営業時間外"
                    operational_info.append(f"状況: {status}")
            
            if enriched_spot.get('price_level'):
                operational_info.append(f"価格帯: {enriched_spot['price_level']}")
            
            if enriched_spot.get('accessibility'):
                operational_info.append(f"アクセス: {enriched_spot['accessibility']}")
            
            if enriched_spot.get('business_notice'):
                operational_info.append(f"注意: {enriched_spot['business_notice']}")
            
            if operational_info:
                spot_info += "・運営情報: " + " | ".join(operational_info) + "\n"
            
            # 評価情報（信頼性判断に重要）
            if enriched_spot.get('rating'):
                rating_text = f"評価{enriched_spot['rating']}"
                if enriched_spot.get('review_count'):
                    rating_text += f"({enriched_spot['review_count']}件)"
                spot_info += f"・評価: {rating_text}\n"
            
            # 特徴・魅力（体験価値の説明）
            if enriched_spot['description']:
                spot_info += f"・特徴: {enriched_spot['description'][:150]}{'...' if len(enriched_spot['description']) > 150 else ''}\n"
            
            # 写真情報（視覚的魅力）
            if enriched_spot['photos']:
                spot_info += f"・写真: {len(enriched_spot['photos'])}枚の投稿写真あり\n"
            
            # 座標情報（移動計画用）
            if enriched_spot['coordinates']['lat'] and enriched_spot['coordinates']['lng']:
                spot_info += f"・位置: 緯度{enriched_spot['coordinates']['lat']}, 経度{enriched_spot['coordinates']['lng']}\n"
            
            results.append(spot_info.strip())

        found_count = len(results)
        
        # LLMが活用しやすい形式でレスポンスを構成
        response = f"""【検索結果サマリー】
発見件数: {found_count}件のスポット
検索条件: {f"エリア:{area} " if area else ""}{f"カテゴリ:{category} " if category else ""}{f"キーワード:{keywords}" if keywords else ""}

【活用可能なスポット詳細】
{chr(10).join(results)}

【LLM処理指示】
上記の詳細情報を活用して、ユーザーの要求に応じた体験提案を行ってください。
・営業時間を考慮した時間軸の提案
・評価と特徴を踏まえた魅力的な紹介
・位置情報を活用した移動計画
・価格帯を考慮した予算感の提示
・写真情報を活用した視覚的な魅力の説明
詳細情報が豊富に含まれているため、「詳細情報はまだ提供されていません」等の表現は使用しないでください。"""
        
        logger.info(f"search_creator_spots found {found_count} spots with structured details for LLM processing")
        return response

    except Exception as e:
        logger.error(f"Error in search_creator_spots tool: {e}")
        return "スポット検索中にエラーが発生しました。もう一度お試しください。" 