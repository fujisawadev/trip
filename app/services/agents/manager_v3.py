"""
V3 Agent Manager - 改良版
LangGraph 0.4.8の最新機能を使用して、高性能なReActエージェントを構築します。
クリエイター中心の旅行コンシェルジュ機能を提供します。
"""
import os
import logging
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage

from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv
from dataclasses import asdict

from app.services.agents.prompts import QuickPromptGenerator
from app.services.agents.tools.spot_db_search import search_creator_spots
from app.services.agents.tools.tavily_search import web_search_with_context

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class AgentManagerV3:
    def __init__(self):
        """
        LangGraph 0.4.8の最新機能を使用してReActエージェントを初期化
        """
        # 1. 新しいツールの準備
        self.tools = [search_creator_spots, web_search_with_context]
        
        # 2. モデルの準備
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.error("OPENAI_API_KEY is not set.")
            raise ValueError("OPENAI_API_KEY is not set.")
        
        # GPT-4oを使用（最新のモデル）
        self.model = ChatOpenAI(
            api_key=openai_api_key, 
            model="gpt-4o", 
            temperature=0.1,  # 少し創造性を持たせる
            max_tokens=2000   # 十分な応答長を確保
        )
        
        # 3. システムプロンプトの設定（思考フレームワーク強化版）
        system_prompt = """あなたは、クリエイターのスポット情報を活用する、プロの旅行コンシェルジュです。

【あなたの役割】
ユーザーの質問に対し、クリエイターが登録したスポット情報を最優先で活用して、魅力的で具体的な旅行プランや情報を提供します。クリエイターの視点やおすすめを、あなた自身の言葉で生き生きと伝えてください。

【基本原則】
1. **クリエイターファースト**: 必ず最初にクリエイターのデータベースを検索し、関連情報があればそれを基に応答してください。
2. **Web検索は補助**: クリエイター情報だけでは不十分な場合（例: 営業時間の詳細、最新のイベント情報など）に限って、補助的にWeb検索を利用します。
3. **対話による意図の明確化**: ユーザーの質問が曖昧な場合（例：「どこかおすすめは？」「プランを立てて」）、まずエリアや興味などの好みを追加で質問し、ユーザーの意図を明確にしてから具体的な提案を行ってください。
4. **ツール利用の厳格化**: `search_creator_spots` ツールを利用する際、`category` や `keywords` パラメータは、ユーザーが明確にそのカテゴリやキーワードに言及した場合にのみ使用してください。ユーザーのプロフィールや過去の発言から推測してパラメータを追加してはいけません。
5. **ペルソナ**: 親しみやすく、丁寧で、旅行のプロとして信頼できる口調を維持してください。
6. **具体的な提案**: 抽象的な情報ではなく、「ランチには〇〇がおすすめです」「午後は△△を散策してはいかがでしょう」といった、ユーザーがすぐに行動に移せるような具体的な提案を心がけてください。
7. **応答形式**: ユーザーの意図に基づき、箇条書きや段落を適切に使い分け、読みやすい形式で応答してください。
8. **リンク形式の厳格化**: データベースから取得したスポットの「詳細URL」は、必ず相対パス（例: /username/spot_id）としてそのまま使用してください。`http://` や `https://` から始まるドメイン名を勝手に追加してはいけません。Web検索で得た外部リンクはそのまま使用して構いません。
"""
        
        # 4. メモリの設定
        self.memory = MemorySaver()
        
        # 5. ReActエージェントの作成（LangGraph 0.4.8の最新機能）
        self.agent = create_react_agent(
            model=self.model,
            tools=self.tools,
            checkpointer=self.memory,
            prompt=system_prompt
        )
        
        # クイックプロンプトジェネレーターの初期化
        self.prompt_generator = QuickPromptGenerator()
        
        logger.info("AgentManagerV3 initialized with enhanced creator-first approach and prompt generator.")
    
    def handle_message(self, message: str, session_id: str, context: dict = None):
        """
        ユーザーからのメッセージを処理し、ReActエージェントを実行する
        """
        try:
            # コンテキスト情報をメッセージに含める
            enhanced_message = message
            if context:
                context_info = self._format_context(context)
                if context_info:
                    enhanced_message = f"{context_info}\n\nユーザーの質問: {message}"
            
            # --- AGENT LOGGING START ---
            log_header = f"--- AgentManagerV3 Execution (Session: {session_id}) ---"
            logger.info("\n" + "="*80)
            logger.info(log_header)
            logger.info(f"Received User Message: {message}")
            logger.info(f"Context-Enhanced Input:\n{enhanced_message}")
            logger.info("="*80)
            # --- AGENT LOGGING END ---

            # ReActエージェントの実行
            config = {"configurable": {"thread_id": session_id}}
            
            # ストリーミング実行で最終結果を取得
            final_state = None
            chunk_count = 0
            for chunk in self.agent.stream(
                {"messages": [HumanMessage(content=enhanced_message)]},
                config=config
            ):
                chunk_count += 1
                
                # --- AGENT LOGGING START ---
                logger.info(f"\n--- CHUNK {chunk_count}: Keys = {list(chunk.keys())} ---")
                
                # エージェントの思考プロセス（ツール呼び出しなど）をログ出力
                if "agent" in chunk:
                    agent_state = chunk.get("agent", {})
                    if isinstance(agent_state, dict) and agent_state.get('messages'):
                        last_message = agent_state['messages'][-1]
                        if last_message.tool_calls:
                            logger.info("[AGENT ACTION] Decided to call tools:")
                            for tool_call in last_message.tool_calls:
                                logger.info(f"  - Tool: {tool_call['name']}, Args: {tool_call['args']}")
                        else:
                            logger.info(f"[AGENT FINAL RESPONSE] Content: {last_message.content}")

                # ツールの実行結果をログ出力
                if "tools" in chunk:
                    tools_state = chunk.get("tools", {})
                    if isinstance(tools_state, dict) and tools_state.get('messages'):
                        logger.info("[TOOL OUTPUT] Received results from tools:")
                        for tool_message in tools_state['messages']:
                             # ログが長くなりすぎないように500文字に制限
                             content_preview = str(tool_message.content).replace('\n', ' ').strip()
                             logger.info(f"  - From {tool_message.name}: '{content_preview[:500]}...'")
                # --- AGENT LOGGING END ---
                
                final_state = chunk
            
            # --- AGENT LOGGING START ---
            logger.info("\n" + "="*80)
            logger.info(f"Agent Execution Finished. Total Chunks: {chunk_count}")
            
            # 最後のメッセージ（アシスタントの返答）を取得
            response_content = "申し訳ありません。応答の生成に失敗しました。"
            
            if final_state:
                messages = None
                if "messages" in final_state:
                    messages = final_state["messages"]
                elif "agent" in final_state and "messages" in final_state["agent"]:
                    messages = final_state["agent"]["messages"]
                
                if messages and messages[-1]:
                    response_content = messages[-1].content
                    logger.info(f"Final Response Content: {response_content[:200]}...")
                else:
                    logger.warning("Could not extract final response from agent state.")
            else:
                logger.warning("No final state received from agent stream.")
                
            logger.info("="*80 + "\n")
            # --- AGENT LOGGING END ---

            return {
                "success": True,
                "response": response_content,
                "session_id": session_id
            }
            
        except Exception as e:
            logger.error(f"AgentManagerV3 error: {e}", exc_info=True)
            return {
                "success": False,
                "error": "エージェントの処理中にエラーが発生しました。もう一度お試しください。"
            }
    
    def generate_quick_prompts(self, context: dict) -> list:
        """
        コンテキストに基づいてクイックプロンプトを生成します。
        （現在の実装はv1互換の静的生成です）
        """
        try:
            prompts = []
            page_type = context.get('page_type')

            if page_type == 'profile':
                influencer_info = context.get('influencer_info', {})
                spots = context.get('spots', [])
                prompts = self.prompt_generator.generate_for_profile(influencer_info, spots)
            elif page_type == 'spot_detail':
                spot_info = context.get('spot_info', {})
                # 'user'キーは_serialize_spotによって追加される
                influencer_info = spot_info.get('user', {}) 
                prompts = self.prompt_generator.generate_for_spot(spot_info, influencer_info)
            else:
                prompts = self.prompt_generator._get_fallback_prompts()
            
            return [asdict(prompt) for prompt in prompts]
        except Exception as e:
            logger.error(f"Quick prompt generation error in v3: {e}", exc_info=True)
            return []

    def _format_context(self, context: dict) -> str:
        """
        コンテキスト情報を読みやすい形式にフォーマット
        """
        context_parts = []
        
        if context.get("page_type") == "profile" and context.get("influencer_info"):
            influencer = context["influencer_info"]
            context_parts.append(f"クリエイター: {influencer.get('slug', 'Unknown')}")
            if influencer.get("bio"):
                context_parts.append(f"プロフィール: {influencer['bio']}")
            
            # スポット一覧と登録日時、エリア情報を含める
            spots = context.get("spots", [])
            if spots:
                context_parts.append(f"登録スポット数: {len(spots)}件")
                
                # エリア情報の分析
                areas = set()
                categories = set()
                for spot in spots:
                    # formatted_addressを使用（修正）
                    if spot.get('formatted_address'):
                        address = spot['formatted_address']
                        if '県' in address:
                            area = address.split('県')[0] + '県'
                        elif '府' in address:
                            area = address.split('府')[0] + '府'
                        elif '都' in address:
                            area = address.split('都')[0] + '都'
                        else:
                            area = address.split('、')[0] if '、' in address else address
                        areas.add(area)
                    
                    # カテゴリ情報の収集
                    if spot.get('category'):
                        categories.add(spot['category'])
                
                if areas:
                    context_parts.append(f"主要エリア: {', '.join(sorted(areas))}")
                
                if categories:
                    context_parts.append(f"主要カテゴリ: {', '.join(sorted(categories))}")
                
                # クリエイターの世界観分析
                creator_style = self._analyze_creator_style(spots, influencer)
                if creator_style:
                    context_parts.append(f"クリエイターの特徴: {creator_style}")
                
                # 最近のスポット3件を表示（created_atでソート）
                recent_spots = sorted(
                    [s for s in spots if s.get('created_at')], 
                    key=lambda x: x['created_at'], 
                    reverse=True
                )[:3]
                if recent_spots:
                    context_parts.append("最近の投稿（詳細情報付き）:")
                    for spot in recent_spots:
                        created_date = spot['created_at'][:10] if spot.get('created_at') else '不明'
                        area_info = f" ({spot.get('summary_location') or spot.get('formatted_address', '').split('、')[0]})" if spot.get('summary_location') or spot.get('formatted_address') else ""
                        
                        # 基本情報
                        spot_detail = f"- {spot.get('name', '不明')} ({created_date}){area_info}"
                        
                        # 詳細情報を追加
                        details = []
                        if spot.get('description'):
                            details.append(f"説明: {spot['description'][:50]}{'...' if len(spot['description']) > 50 else ''}")
                        if spot.get('category'):
                            details.append(f"カテゴリ: {spot['category']}")
                        if spot.get('rating'):
                            details.append(f"評価: {spot['rating']}")

                        # 詳細URLをコンテキストに追加
                        user_info = spot.get('user', {})
                        slug = user_info.get('slug') or user_info.get('username')
                        if slug and spot.get('id'):
                             details.append(f"URL: /{slug}/{spot.get('id')}")
                        
                        if details:
                            spot_detail += f" | " + " | ".join(details)
                        
                        context_parts.append(spot_detail)
        
        elif context.get("page_type") == "spot_detail" and context.get("spot_info"):
            spot = context["spot_info"]
            context_parts.append(f"現在のスポット: {spot.get('name', 'Unknown')}")
            if spot.get("description"):
                context_parts.append(f"スポット説明: {spot['description']}")
            # formatted_addressを使用（修正）
            if spot.get("formatted_address"):
                context_parts.append(f"住所: {spot['formatted_address']}")
                # エリア情報を抽出
                address = spot['formatted_address']
                if '県' in address or '府' in address or '都' in address:
                    area = address.split('、')[0] if '、' in address else address.split()[0]
                    context_parts.append(f"エリア: {area}")
            if spot.get("created_at"):
                created_date = spot['created_at'][:10]
                context_parts.append(f"投稿日: {created_date}")
        
        if context_parts:
            return "【コンテキスト情報】\n" + "\n".join(context_parts)
        
        return "" 
    
    def _analyze_creator_style(self, spots: list, influencer: dict) -> str:
        """クリエイターの世界観を分析"""
        try:
            style_indicators = []
            
            # プロフィールから分析
            bio = influencer.get('bio', '')
            if '子連れ' in bio or 'ファミリー' in bio or 'キッズ' in bio:
                style_indicators.append('ファミリー向け')
            if '高級' in bio or 'ラグジュアリー' in bio or 'プレミアム' in bio:
                style_indicators.append('高級志向')
            if 'カジュアル' in bio or 'アウトドア' in bio:
                style_indicators.append('カジュアル')
            
            # スポットのカテゴリから分析
            categories = [spot.get('category', '') for spot in spots]
            category_text = ' '.join(categories)
            
            if 'ホテル' in category_text or '宿泊' in category_text:
                style_indicators.append('宿泊重視')
            if 'カフェ' in category_text:
                style_indicators.append('カフェ好き')
            if 'レストラン' in category_text or '飲食' in category_text:
                style_indicators.append('グルメ重視')
            if '観光' in category_text or '名所' in category_text:
                style_indicators.append('観光スポット重視')
            
            return ', '.join(style_indicators) if style_indicators else ''
            
        except Exception as e:
            logger.error(f"Creator style analysis error: {e}")
            return '' 