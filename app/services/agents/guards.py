"""
AIエージェント ガードレール機能

不適切な入力や出力を防ぎ、サービスの安全性と信頼性を確保します。
"""

import re
import logging
from typing import Dict, List, Tuple, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ViolationType(Enum):
    """違反タイプの分類"""
    INAPPROPRIATE_CONTENT = "inappropriate_content"  # 不適切なコンテンツ
    OFF_TOPIC = "off_topic"  # 話題逸脱
    PERSONAL_INFO = "personal_info"  # 個人情報関連
    COMMERCIAL_SPAM = "commercial_spam"  # 商業的スパム
    HARMFUL_REQUEST = "harmful_request"  # 有害な依頼

class GuardRails:
    """エージェント用ガードレール"""
    
    def __init__(self):
        # 禁止キーワードパターン
        self.inappropriate_patterns = [
            r'(?i)(政治|選挙|宗教|暴力|差別)',
            r'(?i)(個人情報|住所|電話番号|メール)',
            r'(?i)(投資|株|FX|仮想通貨|儲け)',
            r'(?i)(薬|サプリ|健康食品|治療)',
        ]
        
        # 旅行関連キーワード（許可リスト）
        self.travel_keywords = [
            '旅行', '観光', 'スポット', '場所', '行き方', 'アクセス',
            'ホテル', '宿泊', 'レストラン', '食事', 'グルメ',
            '写真', '景色', '見どころ', 'おすすめ', '予算', '時間',
            '移動', '交通', '電車', 'バス', '車', '飛行機',
            '季節', '天気', '服装', '持ち物', '予約', '営業時間'
        ]
    
    def validate_input(self, message: str, context: Dict) -> Tuple[bool, Optional[ViolationType], str]:
        """
        入力メッセージのバリデーション
        
        Returns:
            (is_valid, violation_type, reason)
        """
        try:
            message = message.strip()
            
            # 空メッセージチェック
            if not message:
                return False, ViolationType.INAPPROPRIATE_CONTENT, "空のメッセージは処理できません"
            
            # 長すぎるメッセージチェック
            if len(message) > 1000:
                return False, ViolationType.INAPPROPRIATE_CONTENT, "メッセージが長すぎます（1000文字以内）"
            
            # 不適切コンテンツチェック
            for pattern in self.inappropriate_patterns:
                if re.search(pattern, message):
                    logger.warning(f"Inappropriate content detected: pattern={pattern}")
                    return False, ViolationType.INAPPROPRIATE_CONTENT, "申し訳ありませんが、その内容についてはお答えできません"
            
            # 旅行関連かチェック
            is_travel_related = any(keyword in message for keyword in self.travel_keywords)
            
            # 完全に関係ない質問のチェック
            non_travel_patterns = [
                r'(?i)(ニュース|最新情報|今日|昨日)',
                r'(?i)(計算|数学|プログラム|コード)',
                r'(?i)(天気予報|明日の天気)',  # 旅行コンテキスト外での天気
            ]
            
            for pattern in non_travel_patterns:
                if re.search(pattern, message) and not is_travel_related:
                    return False, ViolationType.OFF_TOPIC, "旅行やスポットに関する質問をお願いします"
            
            return True, None, ""
            
        except Exception as e:
            logger.error(f"Input validation error: {e}")
            return False, ViolationType.INAPPROPRIATE_CONTENT, "メッセージの処理中にエラーが発生しました"
    
    def validate_output(self, response: str, context: Dict) -> Tuple[bool, str]:
        """
        出力レスポンスのバリデーション
        
        Returns:
            (is_valid, sanitized_response)
        """
        try:
            if not response or not response.strip():
                return False, "申し訳ありませんが、適切な回答を生成できませんでした。別の質問をお試しください。"
            
            # 不適切な内容が含まれていないかチェック
            for pattern in self.inappropriate_patterns:
                if re.search(pattern, response):
                    logger.warning(f"Inappropriate output detected: pattern={pattern}")
                    return False, "申し訳ありませんが、適切な回答を生成できませんでした。別の質問をお試しください。"
            
            # レスポンスの長さ制限
            if len(response) > 2000:
                logger.warning(f"Response too long: {len(response)} chars")
                return False, "申し訳ありませんが、回答が長すぎます。より具体的な質問をお願いします。"
            
            # 基本的なサニタイゼーション
            sanitized = response.strip()
            
            # 礼儀正しい語尾の確保
            if not sanitized.endswith(('。', '！', '？', 'です', 'ます', 'ね', 'よ')):
                if not sanitized.endswith('.'):
                    sanitized += "。"
            
            return True, sanitized
            
        except Exception as e:
            logger.error(f"Output validation error: {e}")
            return False, "申し訳ありませんが、回答の処理中にエラーが発生しました。"
    
    def get_rejection_message(self, violation_type: ViolationType, context: Dict) -> str:
        """違反タイプに応じた適切な拒否メッセージを生成"""
        
        base_messages = {
            ViolationType.INAPPROPRIATE_CONTENT: "申し訳ありませんが、その内容についてはお答えできません。",
            ViolationType.OFF_TOPIC: "旅行や観光スポットに関する質問をお願いします。",
            ViolationType.PERSONAL_INFO: "個人情報に関するご質問にはお答えできません。",
            ViolationType.COMMERCIAL_SPAM: "商業的な勧誘に関するご質問にはお答えできません。",
            ViolationType.HARMFUL_REQUEST: "申し訳ありませんが、その依頼にはお応えできません。",
        }
        
        base_message = base_messages.get(violation_type, "申し訳ありませんが、適切な回答ができません。")
        
        # コンテキストに応じたヘルプメッセージ追加
        help_message = "\n\n例えば、「このスポットへの行き方を教えて」「おすすめのレストランはありますか？」「周辺の観光地を知りたい」などをお聞きください。"
        
        return base_message + help_message 