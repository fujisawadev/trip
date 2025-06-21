"""
改良版Tavily検索ツール - クリエイター世界観フィルター対応

Web検索による最新情報の取得と、クリエイターの世界観に合った結果のフィルタリングを行います。
"""

import logging
import os
from typing import Dict, List, Optional
from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class TavilySearchTool:
    """Tavily検索ツールのラッパー"""
    
    def __init__(self):
        self.api_key = os.getenv('TAVILY_API_KEY')
        if not self.api_key:
            logger.error("TAVILY_API_KEY not found in environment variables")
            raise ValueError("TAVILY_API_KEY is required")
        
        self.tool = TavilySearchResults(
            api_key=self.api_key,
            max_results=5,  # フィルタリング前により多く取得
            search_depth="advanced"
        )
        
        # フィルタリング用のLLM
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            self.llm = ChatOpenAI(
                api_key=openai_api_key,
                model="gpt-4o-mini",  # コスト効率を考慮
                temperature=0.1
            )
        else:
            self.llm = None
    
    def search(self, query: str, location_context: Optional[str] = None) -> Dict:
        """
        Web検索を実行
        
        Args:
            query: 検索クエリ
            location_context: 位置情報コンテキスト
            
        Returns:
            検索結果の辞書
        """
        try:
            # 位置情報がある場合は検索クエリを強化
            if location_context:
                enhanced_query = f"{query} {location_context}"
            else:
                enhanced_query = query
            
            logger.info(f"Tavily search: {enhanced_query}")
            
            # 検索実行
            results = self.tool.run(enhanced_query)
            
            # 結果を整形
            formatted_results = []
            if isinstance(results, list):
                for result in results:
                    if isinstance(result, dict):
                        formatted_results.append({
                            'title': result.get('title', ''),
                            'content': result.get('content', ''),
                            'url': result.get('url', ''),
                            'score': result.get('score', 0)
                        })
            
            return {
                'success': True,
                'query': enhanced_query,
                'results': formatted_results,
                'count': len(formatted_results)
            }
            
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return {
                'success': False,
                'error': str(e),
                'query': query,
                'results': [],
                'count': 0
            }
    
    def search_with_context_filter(self, query: str, creator_context: str, location: str = None) -> str:
        """
        クリエイター世界観を考慮した検索とフィルタリング
        
        Args:
            query: 検索クエリ
            creator_context: クリエイターの世界観情報
            location: 検索地域
            
        Returns:
            フィルタリングされた検索結果の文字列
        """
        try:
            # 検索実行
            search_results = self.search(query, location)
            
            if not search_results['success'] or not search_results['results']:
                return f"「{query}」の検索結果が見つかりませんでした。"
            
            # LLMによる世界観フィルタリング
            if self.llm and creator_context:
                filter_prompt = f"""
以下の検索結果から、クリエイターの世界観に最も合うものを3つ選んで、おすすめ順に整理してください。

【クリエイターの特徴】
{creator_context}

【検索結果】
{self._format_search_results(search_results['results'])}

【出力形式】
各おすすめについて：
- タイトル
- 理由（なぜこのクリエイターにマッチするか）
- 詳細情報
- URL（必要に応じて）

簡潔で親しみやすい文章でお答えください。
"""
                
                try:
                    filtered_response = self.llm.invoke(filter_prompt).content
                    return filtered_response
                except Exception as e:
                    logger.error(f"Context filtering error: {e}")
                    # フィルタリングに失敗した場合は元の結果を返す
                    return self._format_search_results(search_results['results'])
            else:
                # LLMが利用できない場合は元の結果を返す
                return self._format_search_results(search_results['results'])
                
        except Exception as e:
            logger.error(f"Context search error: {e}")
            return f"検索中にエラーが発生しました: {str(e)}"
    
    def _format_search_results(self, results: List[Dict]) -> str:
        """検索結果を読みやすい形式に整形"""
        if not results:
            return "検索結果がありません。"
        
        formatted = []
        for i, result in enumerate(results[:3], 1):
            formatted.append(f"""
{i}. **{result.get('title', '不明')}**
{result.get('content', '詳細情報なし')[:200]}{'...' if len(result.get('content', '')) > 200 else ''}
URL: {result.get('url', '')}
""".strip())
        
        return "\n\n".join(formatted)
    
    def is_available(self) -> bool:
        """ツールが利用可能かチェック"""
        return bool(self.api_key)
    
    def get_description(self) -> str:
        """ツールの説明を取得"""
        return "最新の観光情報、営業時間、イベント情報などをWeb検索で取得し、クリエイターの世界観に合った結果を提供します"

# LangChainツール形式での統合
@tool
def web_search_with_context(query: str, creator_context: str = "", location: str = "") -> str:
    """
    Web検索を実行し、クリエイターの世界観に合った結果を返します。
    最新の観光情報、営業時間、イベント情報、混雑状況などを取得できます。
    
    :param query: 検索したい内容（例: "大阪 プール付きホテル", "京都 カフェ 営業時間"）
    :param creator_context: クリエイターの特徴や世界観（例: "ファミリー向け", "高級志向"）
    :param location: 検索対象の地域（例: "大阪", "東京"）
    :return: クリエイターの世界観に合った検索結果
    """
    try:
        tavily_tool = TavilySearchTool()
        
        if creator_context:
            # クリエイター世界観を考慮した検索
            return tavily_tool.search_with_context_filter(query, creator_context, location)
        else:
            # 通常の検索
            results = tavily_tool.search(query, location)
            if results['success']:
                return tavily_tool._format_search_results(results['results'])
            else:
                return f"検索中にエラーが発生しました: {results.get('error', '不明なエラー')}"
                
    except Exception as e:
        logger.error(f"web_search_with_context error: {e}")
        return f"Web検索中にエラーが発生しました: {str(e)}" 