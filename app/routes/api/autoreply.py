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
        
        print(f"[テスト実行] ユーザー: {current_user.username}(ID: {current_user.id}), メッセージ: '{message}', 有効: {enabled}")
        
        if not message:
            print(f"[エラー] テストメッセージが空です")
            return jsonify({'success': False, 'error': 'メッセージが入力されていません'}), 400
        
        # AIを使ってメッセージを分析
        print(f"[分析開始] メッセージ: '{message[:50]}{'...' if len(message) > 50 else ''}'")
        is_location_question, confidence, reasoning = analyze_message(message)
        print(f"[分析結果] 場所に関する質問: {is_location_question}, 確信度: {confidence:.2f}, 理由: '{reasoning}'")
        
        # 返信メッセージを生成
        profile_url = request.host_url.rstrip('/') + f'/u/{current_user.username}'
        reply_message = template.replace('{profile_url}', profile_url) if is_location_question and enabled and template else ''
        print(f"[返信生成] テンプレート使用: {bool(template)}, プロフィールURL: '{profile_url}'")
        print(f"[返信生成] 最終返信メッセージ: '{reply_message}'")
        
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

@autoreply_bp.route('/send_test', methods=['POST'])
@login_required
def send_test():
    """テスト用のメッセージ送信API"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'success': False, 'error': '無効なリクエスト形式です'}), 400
        
        recipient_id = data.get('recipient_id')
        message = data.get('message')
        
        if not recipient_id:
            return jsonify({'success': False, 'error': '送信先IDが指定されていません'}), 400
        
        if not message:
            return jsonify({'success': False, 'error': 'メッセージが入力されていません'}), 400
        
        # アクセストークンの確認
        access_token = current_user.instagram_token
        if not access_token:
            return jsonify({'success': False, 'error': 'Instagram連携が完了していません'}), 400
        
        print(f"テスト送信を実行: ユーザー={current_user.username}, 送信先ID={recipient_id}")
        success = send_instagram_test_message(access_token, recipient_id, message)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'メッセージの送信に失敗しました'}), 500
            
    except Exception as e:
        print(f"テスト送信中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': 'テスト中にエラーが発生しました'}), 500

def analyze_message(message):
    """メッセージが場所に関する質問かどうかをAIで分析する"""
    try:
        print(f"[analyze_message] 分析開始: '{message[:50]}{'...' if len(message) > 50 else ''}'")
        
        if not openai.api_key:
            # API Keyが設定されていない場合はランダムな結果を返す（開発用）
            import random
            is_location = "場所" in message or "どこ" in message or "スポット" in message
            print(f"[analyze_message] API Key未設定: キーワードベースで判定します")
            result = (is_location, 0.8 if is_location else 0.2, "キーワード検出によるテスト判定")
            print(f"[analyze_message] 結果: {result}")
            return result
        
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
        print(f"[analyze_message] OpenAI API呼び出し準備: モデル=gpt-4o")
        
        # OpenAI APIを呼び出す
        client = openai.OpenAI()
        
        print(f"[analyze_message] API呼び出し開始: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "あなたはメッセージ分析の専門家です。指示に従って分析結果をJSON形式で返してください。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        print(f"[analyze_message] API呼び出し完了: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        print(f"[analyze_message] APIレスポンス: {response.choices[0].message.content}")
        
        # レスポンスを解析
        result = json.loads(response.choices[0].message.content)
        is_location_question = result.get('is_location_question', False)
        confidence = result.get('confidence', 0.0)
        reasoning = result.get('reasoning', '')
        
        print(f"[analyze_message] 最終結果: is_location={is_location_question}, confidence={confidence:.2f}, reasoning='{reasoning}'")
        
        return is_location_question, confidence, reasoning
    
    except Exception as e:
        print(f"[analyze_message] エラー発生: {str(e)}")
        print(traceback.format_exc())
        # エラーの場合はFalseを返す
        return False, 0.0, "分析エラー"

def send_instagram_test_message(access_token, recipient_id, message_text):
    """Instagramにテスト用メッセージを送信する"""
    try:
        url = "https://graph.facebook.com/v22.0/me/messages"
        
        print(f"Instagram APIテスト送信: URL={url}, recipient_id={recipient_id}, トークン長さ={len(access_token)}")
        
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text}
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        params = {
            "access_token": access_token
        }
        
        print(f"テスト送信ペイロード: {json.dumps(payload)}")
        
        response = requests.post(url, headers=headers, params=params, json=payload)
        
        print(f"Instagram API応答: ステータスコード {response.status_code}, レスポンス {response.text}")
        
        if response.status_code == 200:
            print("Instagram返信テスト送信成功")
            return True
        else:
            print(f"Instagram返信テスト送信失敗: ステータスコード {response.status_code}, レスポンス {response.text}")
            return False
        
    except Exception as e:
        print(f"Instagram返信テスト送信中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        return False 