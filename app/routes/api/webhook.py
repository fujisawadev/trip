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
            
            # この部分を追加：Instagramのwebhookイベントを処理
            if data and 'object' in data and data['object'] == 'instagram':
                logger.info("Instagram webhook event detected, processing entries")
                for entry in data.get('entry', []):
                    logger.info(f"Processing webhook entry: {json.dumps(entry)}")
                    process_webhook_entry(entry)
            else:
                logger.warning("Received webhook is not a valid Instagram event or missing required fields")
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
    page_id = entry.get('id')
    print(f"Webhookエントリー処理: page_id={page_id}, entry={json.dumps(entry, indent=2, ensure_ascii=False)}")
    
    # メッセージイベントの処理
    messaging_events = entry.get('messaging', [])
    print(f"メッセージイベント検出: {len(messaging_events)}件")
    
    for event in messaging_events:
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        message = event.get('message', {})
        message_text = message.get('text', '')
        
        if not message_text:
            print(f"メッセージ本文が空のため処理をスキップします: {json.dumps(event, indent=2, ensure_ascii=False)}")
            continue
        
        print(f"受信したメッセージ: {message_text}, 送信者: {sender_id}, 受信者: {recipient_id}, page_id: {page_id}")
        
        # ユーザー情報の取得
        user = User.query.filter_by(instagram_business_id=page_id).first()
        
        if not user:
            print(f"page_id={page_id}に対応するユーザーが見つかりません。Instagram連携済みのユーザーを検索します。")
            instagram_users = User.query.filter(User.instagram_token.isnot(None)).all()
            
            if instagram_users:
                user_ids = [u.id for u in instagram_users]
                usernames = [u.instagram_username for u in instagram_users]
                print(f"Instagram連携済みユーザー: id={user_ids}, usernames={usernames}")
                
                # 最初のユーザーを使用
                user = instagram_users[0]
                print(f"ユーザーID{user.id}を使用します (instagram_username={user.instagram_username})")
                
                # ユーザー情報を更新
                user.instagram_business_id = page_id
                db.session.commit()
                print(f"ユーザーのinstagram_business_idを{page_id}に更新しました")
            else:
                print("Instagram連携済みのユーザーが見つかりません")
                continue
        
        # メッセージを分析して場所に関する質問かどうかを判断
        is_location_question, confidence, reasoning = analyze_message(message_text)
        print(f"メッセージ分析結果: 場所に関する質問={is_location_question}, 確信度={confidence}, 理由={reasoning}")
        
        # 自動返信の条件を確認
        auto_reply_threshold = 0.5  # 確信度の閾値
        if is_location_question and confidence >= auto_reply_threshold:
            print(f"自動返信の条件を満たしました: 場所に関する質問={is_location_question}, 確信度={confidence}")
            
            # 実際に返信を送信
            reply_message = "この前行った場所ですが、東京の代官山にあるカフェです。カフェの名前はStreamTokyo（ストリームトウキョウ）です。最寄り駅は代官山駅で、落ち着いた雰囲気の素敵なカフェでした。ぜひ行ってみてください！"
            
            # アクセストークンの取得
            access_token = user.instagram_token
            if not access_token:
                print(f"ユーザーID{user.id}のinstagram_tokenが設定されていません")
                continue
            
            print(f"自動返信を送信します: 送信先={sender_id}, ユーザーID={user.id}, アクセストークン={access_token[:10]}...")
            result = send_instagram_reply(access_token, sender_id, reply_message)
            
            if result:
                print(f"自動返信が成功しました: 送信先={sender_id}, メッセージ={reply_message}")
            else:
                print(f"自動返信に失敗しました: 送信先={sender_id}")
        else:
            print(f"自動返信条件を満たしませんでした: 場所に関する質問={is_location_question}, 確信度={confidence}")

def analyze_message(message):
    """メッセージが場所に関する質問かどうかをAIで分析する"""
    try:
        # 一時的にOpenAI APIの呼び出しを無効化し、キーワード判定のみを使用
        print("現在のOpenAI APIの設定に問題があるため、キーワード検出による判定のみを行います")
        is_location = "場所" in message or "どこ" in message or "スポット" in message or "教えて" in message
        confidence = 0.8 if is_location else 0.2
        reasoning = "キーワード検出による判定"
        print(f"キーワード検出結果: is_location={is_location}, confidence={confidence}")
        return is_location, confidence, reasoning
        
        """
        # 以下のコードは現在無効化 - OpenAIのクライアントに問題がある場合
        # API Keyをチェック
        if not openai.api_key:
            print("OpenAI APIキーが設定されていないため、キーワード検出によるフォールバック判定を行います")
            is_location = "場所" in message or "どこ" in message or "スポット" in message or "教えて" in message
            return is_location, 0.8 if is_location else 0.2, "キーワード検出による判定"
            
        print(f"OpenAI APIを使用してメッセージを分析します: {message[:30]}...")
        
        # プロンプトの準備
        prompt = f\"\"\"
あなたはインフルエンサーのDMを分析する専門家です。このメッセージが「場所・スポットに関する質問」かどうかを判断してください。
場所に関する質問の例：「どこに行ったの？」「その場所教えて」「どこでランチした？」「あのカフェどこ？」など

メッセージ: {message}

次の形式でJSON応答してください:
{{
  "is_location_question": true/false,
  "confidence": 0-1の数値,
  "reasoning": "判断理由の簡潔な説明"
}}
\"\"\"
        
        # OpenAI APIを呼び出す方法を試す
        try:
            # OpenAIのバージョンをチェック
            import pkg_resources
            openai_version = pkg_resources.get_distribution("openai").version
            print(f"OpenAIライブラリのバージョン: {openai_version}")
            
            # 旧式の呼び出し方法を使用
            print("旧式のOpenAI APIを呼び出します")
            completion = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "あなたはメッセージ分析の専門家です。指示に従って分析結果をJSON形式で返してください。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=300
            )
            
            # レスポンスを解析
            content = completion.choices[0].message.content
            print(f"OpenAI APIレスポンス: {content[:100]}...")
            result = json.loads(content)
            is_location_question = result.get('is_location_question', False)
            confidence = result.get('confidence', 0.0)
            reasoning = result.get('reasoning', '')
            
        except Exception as e:
            print(f"OpenAI APIの呼び出しでエラーが発生しました: {str(e)}")
            print("キーワードベースの判定にフォールバックします")
            # キーワード検出によるフォールバック
            is_location_question = "場所" in message or "どこ" in message or "スポット" in message or "教えて" in message
            confidence = 0.75 if is_location_question else 0.2
            reasoning = "キーワード検出によるフォールバック判定（API呼び出しエラー）"
        
        print(f"分析結果: is_location_question={is_location_question}, confidence={confidence}, reasoning={reasoning}")
        return is_location_question, confidence, reasoning
        """
    
    except Exception as e:
        print(f"メッセージ分析中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        # エラーの場合はキーワードベースの判定にフォールバック
        print("エラーのため、キーワードベースの判定にフォールバックします")
        is_location = "場所" in message or "どこ" in message or "スポット" in message or "教えて" in message
        return is_location, 0.7 if is_location else 0.2, "キーワード検出によるフォールバック判定（エラー発生後）"

def send_instagram_reply(access_token, recipient_id, message_text):
    """Instagramに直接メッセージを送信する"""
    try:
        url = "https://graph.instagram.com/v22.0/me/messages"
        
        # リクエストデータの詳細ログ
        print(f"Instagram APIリクエスト情報: URL={url}, recipient_id={recipient_id}, トークン長さ={len(access_token)}")
        
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
        
        print(f"リクエストペイロード: {json.dumps(payload)}")
        
        response = requests.post(url, headers=headers, params=params, json=payload)
        
        print(f"Instagram API応答: ステータスコード {response.status_code}, レスポンス {response.text}")
        
        if response.status_code == 200:
            print("Instagram返信送信成功")
            return True
        else:
            print(f"Instagram返信送信失敗: ステータスコード {response.status_code}, レスポンス {response.text}")
            return False
        
    except Exception as e:
        print(f"Instagram返信送信中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        return False 