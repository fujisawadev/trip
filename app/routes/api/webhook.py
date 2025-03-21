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
    try:
        from flask_wtf.csrf import CSRFProtect
        print(f"Trying to configure webhook: app={app}, type={type(app)}")
        print(f"App has extensions: {hasattr(app, 'extensions')}")
        if hasattr(app, 'extensions'):
            print(f"Available extensions: {app.extensions.keys()}")
        
        csrf = app.extensions.get('csrf', None)
        print(f"CSRF object: {csrf}, type={type(csrf)}")
        
        if csrf:
            csrf.exempt(webhook_bp)
            app.logger.info("Webhook blueprint is now CSRF exempt")
        else:
            print("Warning: CSRF object not found, webhook may not be properly configured!")
    except Exception as e:
        print(f"Error configuring webhook: {str(e)}")
        import traceback
        traceback.print_exc()

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
    
    # ユーザー情報の取得 - 新API対応: Instagram Business IDで優先的に検索
    user = User.query.filter_by(instagram_business_id=page_id).first()
    
    # 後方互換性のためにFacebook Page IDでも検索
    if not user:
        print(f"instagram_business_id={page_id}に対応するユーザーが見つかりません。Facebook Page IDで検索します。")
        user = User.query.filter_by(facebook_page_id=page_id).first()
    
    # メッセージイベントの処理
    messaging_events = entry.get('messaging', [])
    print(f"メッセージイベント検出: {len(messaging_events)}件")
    
    for event in messaging_events:
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        # メッセージイベントの処理
        if 'message' in event:
            message = event.get('message', {})
            message_text = message.get('text', '')
            
            if message_text:
                print(f"受信したメッセージ: {message_text}, 送信者: {sender_id}, 受信者: {recipient_id}, page_id: {page_id}")
                
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
                        
                        # IDを検出したらユーザー情報を更新（どちらかのIDフィールドを更新）
                        if not user.instagram_business_id:
                            user.instagram_business_id = page_id
                            db.session.commit()
                            print(f"ユーザーのinstagram_business_idを{page_id}に更新しました")
                        elif not user.facebook_page_id:
                            user.facebook_page_id = page_id
                            db.session.commit()
                            print(f"ユーザーのfacebook_page_idを{page_id}に更新しました")
                    else:
                        print("Instagram連携済みのユーザーが見つかりません")
                        continue
                
                # ユーザーの自動返信が有効かチェック
                if not user.autoreply_enabled:
                    print(f"ユーザーID{user.id}の自動返信が無効です")
                    continue
                
                # メッセージを分析して場所に関する質問かどうかを判断
                is_location_question, confidence, reasoning = analyze_message(message_text)
                print(f"メッセージ分析結果: 場所に関する質問={is_location_question}, 確信度={confidence}, 理由={reasoning}")
                
                # 自動返信の条件を確認
                auto_reply_threshold = 0.5
                if is_location_question and confidence >= auto_reply_threshold:
                    print(f"自動返信の条件を満たしました: 場所に関する質問={is_location_question}, 確信度={confidence}")
                    
                    # 返信メッセージのテンプレートを取得
                    template = user.autoreply_template
                    if not template:
                        print(f"ユーザーID{user.id}の返信テンプレートが設定されていません")
                        continue
                    
                    # プロフィールURLを構築
                    profile_url = f"https://{request.host}/u/{user.username}"
                    reply_message = template.replace('{profile_url}', profile_url)
                    
                    # アクセストークンの取得（Instagram APIではInstagramトークンを優先的に使用）
                    access_token = user.instagram_token or user.facebook_token
                    if not access_token:
                        print(f"ユーザーID{user.id}のトークンが設定されていません")
                        continue
                    
                    print(f"自動返信を送信します: 送信先={sender_id}, ユーザーID={user.id}, アクセストークン={access_token[:10]}...")
                    result = send_instagram_reply(access_token, sender_id, reply_message)
                    
                    if result:
                        print(f"自動返信が成功しました: 送信先={sender_id}, メッセージ={reply_message}")
                    else:
                        print(f"自動返信に失敗しました: 送信先={sender_id}")
                else:
                    print(f"自動返信条件を満たしませんでした: 場所に関する質問={is_location_question}, 確信度={confidence}")
            else:
                print(f"メッセージ本文が空のため処理をスキップします: {json.dumps(event, indent=2, ensure_ascii=False)}")
        
        # リアクションイベントの処理
        elif 'reaction' in event:
            reaction = event.get('reaction', {})
            reaction_type = reaction.get('reaction')
            print(f"リアクションを受信: {reaction_type}, 送信者: {sender_id}, 受信者: {recipient_id}")
            # リアクションの処理が必要な場合はここに追加
        
        # その他のイベントタイプ
        else:
            print(f"未処理のイベントタイプ: {json.dumps(event, indent=2, ensure_ascii=False)}")
            
    # フィールドベースのWebhookでも処理できるようにする
    # これはInstagram Graph APIのフィールドベースのWebhookに対応するため
    if 'changes' in entry:
        changes = entry.get('changes', [])
        for change in changes:
            field = change.get('field')
            value = change.get('value', {})
            
            print(f"フィールド変更検出: field={field}, value={json.dumps(value, indent=2, ensure_ascii=False)}")
            
            # messagesフィールドの処理
            if field == 'messages':
                sender_id = value.get('sender', {}).get('id')
                recipient_id = value.get('recipient', {}).get('id')
                message = value.get('message', {})
                message_text = message.get('text', '')
                
                if message_text:
                    print(f"フィールドベースで受信したメッセージ: {message_text}, 送信者: {sender_id}")
                    
                    # ページIDの取得
                    page_id = entry.get('id')
                    
                    # ユーザー情報の取得 - 新API対応: Instagram Business IDで優先的に検索
                    user = User.query.filter_by(instagram_business_id=page_id).first()
                    
                    # 後方互換性のためにFacebook Page IDでも検索
                    if not user:
                        print(f"instagram_business_id={page_id}に対応するユーザーが見つかりません。Facebook Page IDで検索します。")
                        user = User.query.filter_by(facebook_page_id=page_id).first()
                    
                    if not user:
                        print(f"page_id={page_id}に対応するユーザーが見つかりません。Instagram連携済みのユーザーを検索します。")
                        # Instagram連携済みのユーザーを検索
                        instagram_users = User.query.filter(User.instagram_token.isnot(None)).all()
                        if not instagram_users:
                            print("Instagram連携済みのユーザーが見つかりません")
                            continue
                        
                        # 最初のユーザーを使用
                        user = instagram_users[0]
                        
                        # IDを検出したらユーザー情報を更新（どちらかのIDフィールドを更新）
                        if not user.instagram_business_id:
                            user.instagram_business_id = page_id
                            db.session.commit()
                            print(f"ユーザーのinstagram_business_idを{page_id}に更新しました")
                        elif not user.facebook_page_id:
                            user.facebook_page_id = page_id
                            db.session.commit()
                            print(f"ユーザーのfacebook_page_idを{page_id}に更新しました")
                    
                    # ユーザーの自動返信が有効かチェック
                    if not user.autoreply_enabled:
                        print(f"ユーザーID{user.id}の自動返信が無効です")
                        continue
                    
                    # メッセージを分析して場所に関する質問かどうかを判断
                    is_location_question, confidence, reasoning = analyze_message(message_text)
                    print(f"メッセージ分析結果: 場所に関する質問={is_location_question}, 確信度={confidence}, 理由={reasoning}")
                    
                    # 自動返信の条件を確認
                    auto_reply_threshold = 0.5
                    if is_location_question and confidence >= auto_reply_threshold:
                        print(f"自動返信の条件を満たしました: 場所に関する質問={is_location_question}, 確信度={confidence}")
                        
                        # 返信メッセージのテンプレートを取得
                        template = user.autoreply_template
                        if not template:
                            print(f"ユーザーID{user.id}の返信テンプレートが設定されていません")
                            continue
                        
                        # プロフィールURLを構築
                        profile_url = f"https://{request.host}/u/{user.username}"
                        reply_message = template.replace('{profile_url}', profile_url)
                        
                        # アクセストークンの取得（Instagram APIではInstagramトークンを優先的に使用）
                        access_token = user.instagram_token or user.facebook_token
                        if not access_token:
                            print(f"ユーザーID{user.id}のトークンが設定されていません")
                            continue
                        
                        print(f"自動返信を送信します: 送信先={sender_id}, ユーザーID={user.id}, アクセストークン={access_token[:10]}...")
                        result = send_instagram_reply(access_token, sender_id, reply_message)
                        
                        if result:
                            print(f"自動返信が成功しました: 送信先={sender_id}, メッセージ={reply_message}")
                        else:
                            print(f"自動返信に失敗しました: 送信先={sender_id}")
                    else:
                        print(f"自動返信条件を満たしませんでした: 場所に関する質問={is_location_question}, 確信度={confidence}")
                else:
                    print(f"メッセージ本文が空のため処理をスキップします")
            
            # commentsフィールドの処理（必要に応じて追加）
            elif field == 'comments':
                print(f"コメント通知を受信しましたが、現在処理は実装されていません")

def analyze_message(message):
    """メッセージが場所に関する質問かどうかをキーワードベースで分析する"""
    try:
        # キーワードベースでの判定
        print(f"キーワードベースで分析します: {message[:30]}...")
        is_location = any(keyword in message for keyword in ["場所", "どこ", "スポット", "教えて", "行った", "どの辺"])
        confidence = 0.8 if is_location else 0.2
        reasoning = "キーワード検出による判定"
        print(f"キーワード検出結果: is_location={is_location}, confidence={confidence}")
        return is_location, confidence, reasoning
    
    except Exception as e:
        print(f"メッセージ分析中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        # エラーの場合も最低限のキーワード検出を行う
        is_location = "場所" in message or "どこ" in message
        return is_location, 0.7 if is_location else 0.2, "キーワード検出によるフォールバック判定（エラー発生後）"

def send_instagram_reply(access_token, recipient_id, message):
    """Instagramダイレクトメッセージに自動返信を送信する"""
    try:
        instagram_api_version = current_app.config.get('INSTAGRAM_API_VERSION', 'v18.0')
        instagram_api_url = f"https://graph.instagram.com/{instagram_api_version}/me/messages"

        # Instagram API対応のメッセージ送信
        data = {
            'recipient': json.dumps({'id': recipient_id}),
            'message': json.dumps({'text': message}),
            'access_token': access_token
        }

        # ログ記録（トークンを隠す）
        log_data = data.copy()
        log_data['access_token'] = log_data['access_token'][:5] + '...' if log_data['access_token'] else None
        print(f"Instagram APIリクエスト: url={instagram_api_url}, data={json.dumps(log_data, indent=2, ensure_ascii=False)}")

        # POSTリクエスト送信
        response = requests.post(instagram_api_url, data=data)
        
        # レスポンス確認
        if response.status_code == 200:
            print(f"Instagram APIレスポンス成功: status_code={response.status_code}, response={response.text}")
            return True
        else:
            # エラーの詳細をログに記録
            error_message = f"Instagram APIエラー: status_code={response.status_code}, response={response.text}"
            print(error_message)
            
            # Facebookメッセージング互換APIでの送信を試行（後方互換性のため）
            # これは新APIが広く利用可能になるまでの移行期間中に役立ちます
            return send_facebook_message(access_token, recipient_id, message)
    except Exception as e:
        print(f"Instagram APIエラー例外: {str(e)}")
        traceback.print_exc()
        
        # エラー時はFacebookメッセージング互換APIでの送信を試行
        return send_facebook_message(access_token, recipient_id, message)

def send_facebook_message(access_token, recipient_id, message):
    """レガシーFacebookメッセージングAPIを使用して送信（後方互換性用）"""
    try:
        fb_api_version = current_app.config.get('FACEBOOK_API_VERSION', 'v18.0')
        fb_api_url = f"https://graph.facebook.com/{fb_api_version}/me/messages"

        data = {
            'recipient': json.dumps({'id': recipient_id}),
            'message': json.dumps({'text': message}),
            'access_token': access_token
        }

        # ログ記録（トークンを隠す）
        log_data = data.copy()
        log_data['access_token'] = log_data['access_token'][:5] + '...' if log_data['access_token'] else None
        print(f"Facebook APIリクエスト: url={fb_api_url}, data={json.dumps(log_data, indent=2, ensure_ascii=False)}")

        response = requests.post(fb_api_url, data=data)
        
        if response.status_code == 200:
            print(f"Facebook APIレスポンス成功: status_code={response.status_code}, response={response.text}")
            return True
        else:
            error_message = f"Facebook APIエラー: status_code={response.status_code}, response={response.text}"
            print(error_message)
            return False
    except Exception as e:
        print(f"Facebook APIエラー例外: {str(e)}")
        traceback.print_exc()
        return False 