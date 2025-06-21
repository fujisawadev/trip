"""
楽天トラベルツール

既存の楽天API統合を利用してホテル検索を行います。
"""

import logging
from typing import Dict, List, Optional
from app.utils.rakuten_api import search_hotel

logger = logging.getLogger(__name__)

class RakutenTravelTool:
    """楽天トラベルツールのラッパー"""
    
    def __init__(self):
        # 既存のRakuten API統合を利用
        pass
    
    def search_hotels(self, location: str, checkin: str = None, 
                     checkout: str = None, max_results: int = 5) -> Dict:
        """
        ホテル検索を実行
        
        Args:
            location: 検索場所
            checkin: チェックイン日（YYYY-MM-DD）
            checkout: チェックアウト日（YYYY-MM-DD）
            max_results: 最大結果数
            
        Returns:
            ホテル検索結果の辞書
        """
        try:
            logger.info(f"Rakuten hotel search: {location}, checkin={checkin}, checkout={checkout}")
            
            # 既存のsearch_hotel関数を利用
            results = search_hotel(
                keyword=location,
                affiliate_id=None
            )
            
            if 'error' not in results:
                # 楽天APIの戻り値を整形
                hotels = results.get('hotels', [])
                formatted_hotels = []
                
                for hotel in hotels:
                    hotel_basic = hotel.get('hotel', [{}])[0] if hotel.get('hotel') else {}
                    formatted_hotels.append({
                        'name': hotel_basic.get('hotelName', ''),
                        'price': 0,  # 楽天APIでは価格情報が別途必要
                        'rating': hotel_basic.get('userReview', 0),
                        'url': hotel_basic.get('hotelInformationUrl', ''),
                        'address': hotel_basic.get('address1', '') + hotel_basic.get('address2', ''),
                        'access': hotel_basic.get('access', ''),
                        'image_url': hotel_basic.get('hotelImageUrl', '')
                    })
                
                return {
                    'success': True,
                    'location': location,
                    'hotels': formatted_hotels,
                    'count': len(formatted_hotels),
                    'checkin': checkin,
                    'checkout': checkout
                }
            else:
                return {
                    'success': False,
                    'error': results.get('error', 'Unknown error'),
                    'location': location,
                    'hotels': [],
                    'count': 0
                }
                
        except Exception as e:
            logger.error(f"Rakuten hotel search error: {e}")
            return {
                'success': False,
                'error': str(e),
                'location': location,
                'hotels': [],
                'count': 0
            }
    
    def is_available(self) -> bool:
        """ツールが利用可能かチェック"""
        try:
            # 既存のrakuten_api関数の存在をチェック
            from app.utils.rakuten_api import search_hotel
            return True
        except ImportError:
            return False
    
    def get_description(self) -> str:
        """ツールの説明を取得"""
        return "楽天トラベルAPIを使用してホテル・宿泊施設の検索と予約情報を取得します"