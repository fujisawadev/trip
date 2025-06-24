"""
クイックプロンプト生成機能

ユーザーが迷わず質問できるよう、コンテキストに応じた
適切なプロンプト候補を自動生成します。
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class QuickPrompt:
    """クイックプロンプトの構造"""
    text: str
    category: str
    icon: str
    priority: int

class QuickPromptGenerator:
    """コンテキスト対応クイックプロンプト生成器"""
    
    def __init__(self):
        # プロフィールページ用プロンプト（総合窓口）
        self.profile_prompts = [
            QuickPrompt("1日プランを計画して", "planning", "📅", 1),
            QuickPrompt("おすすめを教えて", "recommendation", "⭐", 2),
            QuickPrompt("最近の投稿を教えて", "recent", "📱", 3),
        ]
        
        # スポット詳細ページ用プロンプト（専門科）
        self.spot_prompts = [
            QuickPrompt("ここへの行き方を教えて", "access", "🚶", 1),
            QuickPrompt("営業時間・料金を知りたい", "info", "🎫", 2),
            QuickPrompt("周辺のおすすめスポットは？", "nearby", "📍", 3),
        ]
    
    def generate_for_profile(self, influencer_info: Dict, spots: List[Dict]) -> List[QuickPrompt]:
        """プロフィールページ用のクイックプロンプト生成（総合窓口）"""
        try:
            # 基本の総合窓口プロンプトを返す（3つ）
            return self.profile_prompts[:3]
            
        except Exception as e:
            logger.error(f"Profile prompt generation error: {e}")
            return self._get_fallback_prompts()
    
    def generate_for_spot(self, spot_info: Dict, influencer_info: Dict) -> List[QuickPrompt]:
        """スポット詳細ページ用のクイックプロンプト生成（専門科）"""
        try:
            prompts = self.spot_prompts.copy()
            
            # 優先度順にソート
            prompts.sort(key=lambda x: x.priority)
            
            return prompts  # 基本の3個のプロンプトのみ
            
        except Exception as e:
            logger.error(f"Spot prompt generation error: {e}")
            return self._get_fallback_prompts()
    
    def _get_fallback_prompts(self) -> List[QuickPrompt]:
        """エラー時のフォールバックプロンプト"""
        return [
            QuickPrompt("おすすめの観光スポットを教えて", "general", "🗺️", 1),
            QuickPrompt("旅行のアドバイスが欲しい", "general", "✈️", 2),
            QuickPrompt("アクセス方法を知りたい", "access", "🚶", 3),
        ] 