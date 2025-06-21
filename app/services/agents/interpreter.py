"""
LLM Interpreter

LLMを使用してユーザーの意図を解釈し、対話の状態を更新する責務を負います。
このファイルでは、思考プロセスを複数の「役割（ペルソナ）」に分割し、
それぞれ専門のLLMコールを定義します。
"""
import os
import json
import logging
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)

class LLMInterpreter:
    """LLMによる意図解釈器（マルチペルソナ版）"""

    def __init__(self):
        try:
            self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            self.model = "gpt-4o"
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.client = None

    def _call_llm(self, messages: List[Dict], is_json: bool = True, temperature: float = 0.7) -> Optional[Dict]:
        """LLM呼び出しを共通化するヘルパー関数"""
        if not self.client:
            return None
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"} if is_json else None,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            return json.loads(content) if is_json else {"response": content}
        except Exception as e:
            logger.error(f"Error during LLM call: {e}")
            return None

    # --- ペルソナ1: アナリスト ---
    def determine_intent(self, conversation_history: list, context: Dict) -> Optional[Dict]:
        """ユーザーの意図を分析し、次のアクションを決定する"""
        prompt = self._build_analyst_prompt(context)
        messages = [{"role": "system", "content": prompt}]
        messages.extend(conversation_history)
        
        logger.info("Calling Analyst Persona...")
        return self._call_llm(messages, is_json=True, temperature=0.0)

    def _build_analyst_prompt(self, context: dict) -> str:
        context_str = json.dumps(context.get("influencer_info"), ensure_ascii=False, indent=2)
        return f"""
# あなたの役割
あなたは、ユーザーとAIの会話を分析する超一流の「対話アナリスト」です。あなたの仕事は、会話履歴を読み解き、ユーザーの真の意図を特定し、その意図を達成するために次に何をすべきかを定義することです。

# コンテキスト
ユーザーは、以下のインフルエンサーのページを見ています。
{context_str}

# あなたのタスク
会話の最終的なゴールを定め、そのゴール達成に必要な次のアクションを、以下のJSON形式で出力してください。

# アクションの種類
1.  `ask_question`: ユーザーの意図が不明確な場合。対話を続けるための質問を生成します。
2.  `search_database`: ユーザーの要求に応えるために、インフルエンサーのおすすめスポット情報を検索する必要がある場合。

# 出力形式
```json
{{
  "thought": "ユーザーの意図をどう解釈し、なぜこのアクションを選択したかを記述。",
  "action": {{
    "type": "ask_question" or "search_database",
    "content": "ask_questionの場合は、ユーザーへの具体的な質問文を記述。search_databaseの場合は、検索の目的を記述。",
    "keywords": "search_databaseの場合、DB検索に使うべきキーワードを3つ以内でリストとして記述。"
  }}
}}
```
"""

    # --- ペルソナ3: クリエイティブ・ディレクター ---
    def generate_creative_draft(self, goal: str, db_results: list, conversation_history: list, context: Dict) -> Optional[Dict]:
        """DB検索結果とゴールに基づき、応答の下書きを作成する"""
        prompt = self._build_creative_prompt(goal, db_results, context)
        messages = [{"role": "system", "content": prompt}]
        messages.extend(conversation_history)

        logger.info("Calling Creative Director Persona...")
        return self._call_llm(messages, is_json=True, temperature=0.7)

    def _build_creative_prompt(self, goal: str, db_results: list, context: dict) -> str:
        context_str = json.dumps(context.get("influencer_info"), ensure_ascii=False, indent=2)
        db_results_str = json.dumps(db_results, ensure_ascii=False, indent=2)
        return f"""
# あなたの役割
あなたは、人気インフルエンサーの「クリエイティブ・ディレクター」です。あなたの仕事は、提供された情報とインフルエンサーの世界観に基づき、ユーザーに最高の体験を届けるための応答案を作成することです。

# あなたのタスク
以下の情報に基づき、ユーザーへの応答メッセージの下書きをJSON形式で作成してください。

- **ユーザーのゴール**: {goal}
- **インフルエンサー情報**: {context_str}
- **関連スポット情報 (DB検索結果)**: {db_results_str}

# ルール
- DB検索結果が空、またはゴールに合致しない場合は、その旨を正直に伝え、代替案を提案すること。
- インフルエンサーのスタイルや世界観を強く意識した、魅力的で親しみやすい文章を作成すること。

# 出力形式
```json
{{
  "thought": "これらの情報から、どのように応答を組み立てたかの思考プロセスを記述。",
  "response": "ユーザーへの具体的な応答メッセージを記述。"
}}
```
"""

    # --- ペルソナ4: 品質監査官 ---
    def audit_draft(self, draft: dict, goal: str, conversation_history: list) -> Optional[Dict]:
        """応答の下書きを客観的に評価・修正する"""
        prompt = self._build_auditor_prompt(draft, goal, conversation_history)
        messages = [{"role": "system", "content": prompt}]

        logger.info("Calling Quality Auditor Persona...")
        return self._call_llm(messages, is_json=True, temperature=0.0)

    def _build_auditor_prompt(self, draft: dict, goal: str, conversation_history: list) -> str:
        draft_str = json.dumps(draft, ensure_ascii=False, indent=2)
        history_str = json.dumps(conversation_history, ensure_ascii=False, indent=2)
        return f"""
# あなたの役割
あなたは、AIアシスタントの応答を監査する超優秀な「品質監査官」です。ユーザーに提示する前に、応答の品質が最高水準であることを保証してください。

# 監査対象
- **ユーザーのゴール**: {goal}
- **会話履歴**: {history_str}
- **応答案（下書き）**: {draft_str}

# 評価基準
1.  **ゴール達成**: 下書きは、ユーザーのゴールに完全に応えているか？
2.  **文脈整合性**: 会話の流れとして自然か？
3.  **実現可能性**: 提案は、地理的・時間的に無理がないか？

# 出力形式
評価結果を以下のJSON形式で出力してください。

## 問題がない場合
```json
{{
  "is_ok": true,
  "reason": "評価基準をすべて満たしているため。"
}}
```

## 問題がある場合
```json
{{
  "is_ok": false,
  "reason": "問題点を具体的に記述。",
  "revised_response": "修正後のユーザーへの応答メッセージを記述。"
}}
```
"""

# 以前のメソッドはすべて新しいアーキテクチャでは不要
# def interpret(...)
# def _build_system_prompt(...)
# def _build_messages(...)
# def generate_final_response_prompt(...)
# def generate_response(...) 