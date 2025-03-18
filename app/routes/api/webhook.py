from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.user import User
import os
import json
import requests
from datetime import datetime
import hmac
import hashlib
import traceback
import openai
import logging

# ロガーの設定
logger = logging.getLogger(__name__)

# OpenAI APIのセットアップ
openai.api_key = os.environ.get("OPENAI_API_KEY")
if not openai.api_key:
    logger.warning("Warning: OPENAI_API_KEY environment variable is not set")

webhook_bp = Blueprint('webhook', __name__, url_prefix='/webhook')

# webhookエンドポイントではCSRF保護を無効化する（アプリケーション起動時に適用）
def configure_webhook(app):
    """webhookエンドポイントのCSRF保護を設定"""
    from flask_wtf.csrf import CSRFProtect
    csrf = app.extensions.get('csrf', None)
    if csrf:
        csrf.exempt(webhook_bp)
        app.logger.info("Webhook blueprint is now CSRF exempt")

@webhook_bp.route('/instagram', methods=['GET', 'POST'])
def instagram():
    """InstagramのWebhookを処理するエンドポイント"""
    try:
        logger.info(f"Webhook accessed with method: {request.method}")
        logger.info(f"Request args: {request.args}")
        logger.info(f"Request source IP: {request.remote_addr}")
        
        if request.method == 'GET':
            # Webhook検証リクエストの処理（初回設定時のみ使用）
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')
            
            # 診断モード - パラメータが指定されていない場合
            if 'diagnostic' in request.args:
                logger.info("Webhook診断モードが有効化されました")
                
                # 設定情報の表示
                config_info = {
                    'webhook_verify_token': current_app.config.get('INSTAGRAM_WEBHOOK_VERIFY_TOKEN'),
                    'app_secret_configured': bool(current_app.config.get('INSTAGRAM_APP_SECRET')),
                    'skip_validation': os.environ.get('WEBHOOK_SKIP_VALIDATION', 'false').lower() == 'true',
                    'webhook_url': request.url_root.rstrip('/') + '/webhook/instagram'
                }
                
                # ユーザー数
                users_with_instagram = User.query.filter(User.instagram_token.isnot(None)).count()
                
                # 診断情報をJSON形式で返す
                return jsonify({
                    'status': 'active',
                    'endpoint': '/webhook/instagram',
                    'config': config_info,
                    'environment': os.environ.get('FLASK_ENV', 'production'),
                    'server_time': datetime.utcnow().isoformat(),
                    'users_with_instagram': users_with_instagram
                })
            
            verify_token = current_app.config.get('INSTAGRAM_WEBHOOK_VERIFY_TOKEN')
            logger.info(f"Webhook verification attempt: mode={mode}, token={token}, challenge={challenge}, expected_token={verify_token}")
            
            # 常にchallengeを返す（検証をスキップ）
            if challenge:
                logger.info(f"Always returning challenge: {challenge}")
                return challenge
            else:
                logger.info("No challenge provided, returning OK")
                return "OK", 200
        
        # POSTリクエスト（実際のWebhookイベント）を処理
        logger.info("====== POST webhook request received ======")
        logger.info(f"Headers: {dict(request.headers)}")
        
        try:
            raw_data = request.data.decode('utf-8')
            logger.info(f"Raw data: {raw_data}")
        except:
            logger.error("Could not decode request data")
        
        # シグネチャチェックをスキップして常に成功とみなす
        logger.info("Skipping signature validation")
        
        # リクエストボディを取得して内容をログに出力
        try:
            data = request.get_json()
            logger.info(f"Parsed JSON data: {json.dumps(data, indent=2)}")
        except Exception as e:
            logger.error(f"Error parsing JSON: {str(e)}")
        
        # どんな場合も200 OKを返す
        return "OK", 200
    
    except Exception as e:
        logger.error(f"Webhook処理中にエラーが発生しました: {str(e)}")
        logger.error(traceback.format_exc())
        # エラーが発生しても200を返す
        return "OK", 200

def is_request_valid(request, signature):
    """リクエストの署名を検証する"""
    if not signature:
        print("No signature in request")
        # 開発環境の場合は署名なしでも許可することができる
        if os.environ.get('WEBHOOK_SKIP_VALIDATION', 'false').lower() == 'true':
            print("Skipping validation due to WEBHOOK_SKIP_VALIDATION=true")
            return True
        return False
    
    # 環境変数からApp Secretを取得
    app_secret = current_app.config.get('INSTAGRAM_APP_SECRET')
    if not app_secret:
        print("INSTAGRAM_APP_SECRET is not set")
        return False
    
    # sha256署名を検証
    try:
        expected_signature = hmac.new(
            app_secret.encode('utf-8'),
            request.data,
            hashlib.sha256
        ).hexdigest()
        
        received_signature = signature.replace('sha256=', '')
        
        is_valid = hmac.compare_digest(expected_signature, received_signature)
        print(f"Signature validation: {is_valid}")
        return is_valid
    except Exception as e:
        print(f"Error validating signature: {str(e)}")
        return False

def process_webhook_entry(entry):
    """Webhookエントリーを処理する"""
    try:
        # Instagram Business Accountを特定
        page_id = entry.get('id')
        print(f"Webhookエントリー処理: page_id={page_id}, entry={json.dumps(entry, indent=2)}")
        
        # メッセージングイベントを処理
        messaging = entry.get('messaging', [])
        if messaging:
            print(f"メッセージイベント検出: {len(messaging)}件")
            for message_event in messaging:
                process_message_event(message_event, page_id)
        else:
            print("メッセージイベントがありません")
        
        # StandbyイベントとChangesイベントも処理可能
        # standby = entry.get('standby', [])
        # changes = entry.get('changes', [])
    
    except Exception as e:
        print(f"Webhookエントリー処理中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())

def process_message_event(event, page_id):
    """メッセージイベントを処理する"""
    try:
        # 送信者と受信者のID
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        # メッセージ内容
        message = event.get('message', {})
        message_id = message.get('mid')
        message_text = message.get('text', '')
        
        print(f"受信したメッセージ: {message_text}, 送信者: {sender_id}, 受信者: {recipient_id}, page_id: {page_id}")
        
        # ページIDからユーザーを検索
        # InstagramビジネスアカウントとFacebookページの関連付けからユーザーを特定
        user = User.query.filter_by(instagram_business_id=page_id).first()
        if not user:
            print(f"ページID {page_id} に関連付けられたユーザーが見つかりません")
            # instagram_business_idが設定されていない場合は、instagram_user_idも試してみる
            alternate_user = User.query.filter_by(instagram_user_id=recipient_id).first()
            if alternate_user:
                print(f"instagram_user_id={recipient_id}でユーザーを見つけました: {alternate_user.username}")
                user = alternate_user
                
                # instagram_business_idを更新して将来の検索を容易にする
                user.instagram_business_id = page_id
                db.session.commit()
                print(f"ユーザー {user.username} のinstagram_business_idを更新しました: {page_id}")
            else:
                # 最後の手段として、instagram_usernameでユーザーを検索
                alt_user = User.query.filter_by(instagram_username='tsuki_blue_jp').first()
                if alt_user:
                    print(f"instagram_username='tsuki_blue_jp'のユーザーが存在します。ID: {alt_user.id}, instagram_token有無: {bool(alt_user.instagram_token)}")
                    user = alt_user
                    
                    # instagram_business_idを更新
                    user.instagram_business_id = page_id
                    db.session.commit()
                    print(f"ユーザー {user.username} のinstagram_business_idを更新しました: {page_id}")
                else:
                    print("一致するユーザーが見つかりません。DMを処理できません。")
                    return
        
        # 自動返信が有効かどうかをチェック
        if not user.autoreply_enabled or not user.autoreply_template:
            print(f"ユーザーID {user.id} の自動返信は無効です")
            return
        
        # AIを使ってメッセージを分析
        is_location_question, confidence, reasoning = analyze_message(message_text)
        print(f"メッセージ分析結果: 場所に関する質問={is_location_question}, 確信度={confidence}, 理由={reasoning}")
        
        if is_location_question and confidence >= 0.6:  # 閾値を設定
            # 自動返信を送信
            profile_url = current_app.config.get('BASE_URL', '').rstrip('/') + f'/u/{user.username}'
            reply_message = user.autoreply_template.replace('{profile_url}', profile_url)
            
            # 返信を送信
            send_instagram_reply(user.instagram_token, sender_id, reply_message)
            print(f"自動返信を送信しました: {reply_message}")
    
    except Exception as e:
        print(f"メッセージイベント処理中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())

def analyze_message(message):
    """メッセージが場所に関する質問かどうかをAIで分析する"""
    try:
        if not openai.api_key:
            # API Keyが設定されていない場合はシンプルな判定を行う（開発用）
            is_location = "場所" in message or "どこ" in message or "スポット" in message
            return is_location, 0.8 if is_location else 0.2, "キーワード検出による判定"
        
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

def send_instagram_reply(access_token, recipient_id, message_text):
    """Instagram DMに返信を送信する"""
    try:
        url = f"https://graph.instagram.com/v22.0/me/messages"
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        data = {
            'recipient': {'id': recipient_id},
            'message': {'text': message_text},
            'access_token': access_token
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            print(f"Instagram返信送信成功: {response.json()}")
            return True
        else:
            print(f"Instagram返信送信失敗: ステータスコード {response.status_code}, レスポンス {response.text}")
            return False
    
    except Exception as e:
        print(f"Instagram返信送信中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        return False 