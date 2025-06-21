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
            QuickPrompt("ベストな訪問時間は？", "timing", "⏰", 3),
            QuickPrompt("周辺のおすすめスポットは？", "nearby", "📍", 4),
        ]
        
        # カテゴリ別追加プロンプト
        self.category_prompts = {
            'food': [
                QuickPrompt("おすすめメニューは？", "food", "😋", 5),
                QuickPrompt("価格帯はどのくらい？", "food", "💴", 6),
            ],
            'nature': [
                QuickPrompt("絶景ポイントはどこ？", "nature", "🌄", 5),
                QuickPrompt("天気による影響は？", "nature", "☀️", 6),
            ],
            'culture': [
                QuickPrompt("歴史や背景を教えて", "culture", "🏛️", 5),
                QuickPrompt("体験できることは？", "culture", "🎭", 6),
            ]
        }
    
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
            
            # スポットタイプに応じた専門プロンプトを追加
            spot_type = self._detect_spot_type(spot_info)
            
            if spot_type in self.category_prompts:
                # カテゴリ別プロンプトを1つ追加
                category_prompt = self.category_prompts[spot_type][0]
                prompts.append(category_prompt)
            
            # 優先度順にソート
            prompts.sort(key=lambda x: x.priority)
            
            return prompts[:5]  # 最大5個のプロンプト
            
        except Exception as e:
            logger.error(f"Spot prompt generation error: {e}")
            return self._get_fallback_prompts()
    
    def _detect_spot_type(self, spot_info: Dict) -> str:
        """スポットタイプを検出"""
        name = spot_info.get('name', '').lower()
        description = spot_info.get('description', '').lower()
        text = name + ' ' + description
        
        food_keywords = ['レストラン', 'カフェ', '食事', 'グルメ', '料理']
        nature_keywords = ['公園', '山', '海', '川', '自然', '景色']
        culture_keywords = ['神社', '寺', '博物館', '美術館', '歴史']
        
        if any(keyword in text for keyword in food_keywords):
            return 'food'
        elif any(keyword in text for keyword in nature_keywords):
            return 'nature'
        elif any(keyword in text for keyword in culture_keywords):
            return 'culture'
        else:
            return 'general'
    
    def _get_fallback_prompts(self) -> List[QuickPrompt]:
        """エラー時のフォールバックプロンプト"""
        return [
            QuickPrompt("おすすめの観光スポットを教えて", "general", "🗺️", 1),
            QuickPrompt("旅行のアドバイスが欲しい", "general", "✈️", 2),
            QuickPrompt("アクセス方法を知りたい", "access", "🚶", 3),
        ] 