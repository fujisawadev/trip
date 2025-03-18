from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.user import User
import os
import json
import requests
from datetime import datetime
import traceback
import openai

# OpenAI APIのセットアップ
openai.api_key = os.environ.get("OPENAI_API_KEY")
if not openai.api_key:
    print("Warning: OPENAI_API_KEY environment variable is not set")

autoreply_bp = Blueprint('autoreply', __name__, url_prefix='/api/autoreply')

@autoreply_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """自動返信設定の取得・更新API"""
    try:
        if request.method == 'GET':
            # 現在の設定を取得
            return jsonify({
                'success': True,
                'enabled': current_user.autoreply_enabled or False,
                'template': current_user.autoreply_template or ''
            })
        
        # POSTの場合は設定を更新
        data = request.get_json()
        if data is None:
            return jsonify({'success': False, 'error': '無効なリクエスト形式です'}), 400
        
        # バリデーション
        enabled = data.get('enabled', False)
        template = data.get('template', '')
        
        if enabled and not template:
            return jsonify({'success': False, 'error': '自動返信を有効にするにはテンプレートを入力してください'}), 400
        
        # Instagram連携がされていない場合はエラー
        if enabled and not current_user.instagram_token:
            return jsonify({
                'success': False, 
                'error': 'Instagram連携が完了していません。先にInstagramとの連携を行ってください'
            }), 400
        
        # ユーザー設定を更新
        current_user.autoreply_enabled = enabled
        current_user.autoreply_template = template
        current_user.autoreply_last_updated = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"自動返信設定の更新中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': '設定の更新中にエラーが発生しました'}), 500

@autoreply_bp.route('/test', methods=['POST'])
@login_required
def test():
    """自動返信のテストAPI"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'success': False, 'error': '無効なリクエスト形式です'}), 400
        
        message = data.get('message', '')
        enabled = data.get('enabled', False)
        template = data.get('template', '')
        
        if not message:
            return jsonify({'success': False, 'error': 'メッセージが入力されていません'}), 400
        
        # AIを使ってメッセージを分析
        is_location_question, confidence, reasoning = analyze_message(message)
        
        # 返信メッセージを生成
        profile_url = request.host_url.rstrip('/') + f'/u/{current_user.username}'
        reply_message = template.replace('{profile_url}', profile_url) if is_location_question and enabled and template else ''
        
        return jsonify({
            'success': True,
            'is_location_question': is_location_question,
            'confidence': confidence,
            'reasoning': reasoning,
            'reply_message': reply_message
        })
    
    except Exception as e:
        print(f"自動返信テスト中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': 'テスト中にエラーが発生しました'}), 500

def analyze_message(message):
    """メッセージが場所に関する質問かどうかをAIで分析する"""
    try:
        if not openai.api_key:
            # API Keyが設定されていない場合はランダムな結果を返す（開発用）
            import random
            is_location = "場所" in message or "どこ" in message or "スポット" in message
            return is_location, 0.8 if is_location else 0.2, "キーワード検出によるテスト判定"
        
        # プロンプトの準備
        prompt = f"""
あなたはインフルエンサーのDMを分析する専門家です。このメッセージが「場所・スポットに関する質問」かどうかを判断してください。
場所に関する質問の例：「どこに行ったの？」「その場所教えて」「どこでランチした？」「あのカフェどこ？」など

メッセージ: {message}

次の形式でJSON応答してください:
{{
  "is_location_question": true/false,
  "confidence": 0-1の数値,
  "reasoning": "判断理由の簡潔な説明"
}}
"""
        
        # OpenAI APIを呼び出す
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "あなたはメッセージ分析の専門家です。指示に従って分析結果をJSON形式で返してください。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        
        # レスポンスを解析
        result = json.loads(response.choices[0].message.content)
        is_location_question = result.get('is_location_question', False)
        confidence = result.get('confidence', 0.0)
        reasoning = result.get('reasoning', '')
        
        return is_location_question, confidence, reasoning
    
    except Exception as e:
        print(f"メッセージ分析中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        # エラーの場合はFalseを返す
        return False, 0.0, "分析エラー" 