from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.user import User
from app.models.sent_message import SentMessage
import os
import json
import requests
from datetime import datetime
import hmac
import hashlib
import traceback
import openai
import logging
import time

# ブロックするInstagram IDのリスト
BLOCKED_INSTAGRAM_IDS = ['52002219496815']

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
    """messagingイベントを含むwebhookエントリを処理する"""
    page_id = entry.get('id')
    messaging_events = entry.get('messaging', [])

    # ▼▼▼ 修正点1: ブロックリストによるチェック ▼▼▼
    if page_id in BLOCKED_INSTAGRAM_IDS:
        logger.info(f"Ignoring webhook from blocked Instagram ID: {page_id}")
        return  # ここで処理を完全に終了
    # ▲▲▲ ここまで ▲▲▲
    
    # メッセージがない場合は早期リターン
    if not messaging_events:
        print("メッセージイベントがありません。フィールドベースのwebhookを確認します")
        return process_field_based_webhook(entry)
    
    # まずエコーメッセージをフィルタリング - データベースアクセス前に実行
    filtered_events = []
    for event in messaging_events:
        message = event.get('message', {})
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        # エコーメッセージはスキップ
        if message.get('is_echo') == True:
            print(f"エコーメッセージを検出しました。処理をスキップします: {message.get('text', '')[:50]}...")
            continue
            
        # テキストがないメッセージもスキップ
        if not message.get('text'):
            print("テキストのないメッセージ（画像など）はスキップします")
            continue
            
        # 自動返信メッセージかどうかをチェック（ループ防止）- テキスト内容にかかわらず送信者と受信者の組み合わせをチェック
        if SentMessage.has_recent_message(sender_id, sender_id):
            print(f"24時間以内に自動返信を送信済みの相手からのメッセージです。処理をスキップします。sender_id={sender_id}, recipient_id={recipient_id}")
            continue
            
        # 有効なメッセージだけを追加
        filtered_events.append(event)
    
    # 処理対象のメッセージがない場合は早期リターン
    if not filtered_events:
        print("処理対象のメッセージイベントがありません")
        return
    
    # ここでユーザー情報の取得 - フィルタリング後に実行
    user = get_user_by_ids(page_id)
    
    # ユーザーが見つからない場合は処理終了
    if not user:
        print("有効なユーザーが見つかりません")
        return
    
    # 処理対象のメッセージイベントを処理
    for event in filtered_events:
        process_message_event(event, user)
    
    return

def get_user_by_ids(page_id):
    """複数のIDフィールドを使ってユーザーを検索する"""
    # Instagram Business IDで検索
    user = User.query.filter_by(instagram_business_id=page_id).first()
    if user:
        return user
        
    print(f"instagram_business_id={page_id}に対応するユーザーが見つかりません。instagram_user_idで検索します。")
    
    # Instagram User ID（メッセージング用ID）で検索
    user = User.query.filter_by(instagram_user_id=page_id).first()
    if user:
        return user
        
    print(f"instagram_user_id={page_id}に対応するユーザーも見つかりません。Facebook Page IDで検索します。")
    
    # 後方互換性のためにFacebook Page IDでも検索
    user = User.query.filter_by(facebook_page_id=page_id).first()
    if user:
        return user

    # ▼▼▼ 修正点2: 危険なフォールバック処理を削除 ▼▼▼
    print(f"All attempts to find a user for page_id={page_id} failed. Aborting.")
    return None
    # ▲▲▲ ここまで ▲▲▲

def process_message_event(event, user):
    """メッセージイベントを処理する"""
    sender_id = event.get('sender', {}).get('id')
    recipient_id = event.get('recipient', {}).get('id')
    
    # メッセージイベントの処理
    if 'message' in event:
        message = event.get('message', {})
        message_text = message.get('text', '')
        
        # ここでは message_text が存在することは保証されている（process_webhook_entryでフィルタリング済み）
        print(f"受信したメッセージ: {message_text}, 送信者: {sender_id}, 受信者: {recipient_id}")
        
        # ユーザーの自動返信が有効かチェック
        if not user.autoreply_enabled:
            print(f"ユーザーID{user.id}の自動返信が無効です")
            return
        
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
                return
            
            # プロフィールURLを構築
            profile_url = f"https://{request.host}{user.get_public_url()}"
            reply_message = template.replace('{profile_url}', profile_url)
            
            # Instagram API with Instagram Login対応 - Instagram Tokenを優先して使用
            access_token = user.instagram_token
            if not access_token:
                print(f"ユーザーID{user.id}のInstagramトークンが設定されていません。Facebookトークンを試します。")
                access_token = user.facebook_token
            
            if not access_token:
                print(f"ユーザーID{user.id}のアクセストークンが設定されていません")
                return
            
            print(f"自動返信を送信します: 送信先={sender_id}, ユーザーID={user.id}, アクセストークン={access_token[:10]}...")
            result = send_instagram_reply(access_token, sender_id, reply_message)
            
            if result:
                print(f"自動返信が成功しました: 送信先={sender_id}, メッセージ={reply_message}")
            else:
                print(f"自動返信に失敗しました: 送信先={sender_id}")
        else:
            print(f"自動返信条件を満たしませんでした: 場所に関する質問={is_location_question}, 確信度={confidence}")
    
    # リアクションイベントの処理
    elif 'reaction' in event:
        reaction = event.get('reaction', {})
        reaction_type = reaction.get('reaction')
        print(f"リアクションを受信: {reaction_type}, 送信者: {sender_id}, 受信者: {recipient_id}")
        # リアクションの処理が必要な場合はここに追加
    
    # その他のイベントタイプ
    else:
        print(f"未処理のイベントタイプ: {json.dumps(event, indent=2, ensure_ascii=False)}")

def process_field_based_webhook(entry):
    """フィールドベースのwebhookイベントを処理する"""
    page_id = entry.get('id')
    
    # フィールドベースのWebhookでも処理できるようにする
    # これはInstagram Graph APIのフィールドベースのWebhookに対応するため
    if 'changes' not in entry:
        return
    
    changes = entry.get('changes', [])
    if not changes:
        print("フィールド変更がありません")
        return
        
    # 有効なメッセージ変更のみをフィルタリング
    valid_changes = []
    for change in changes:
        field = change.get('field')
        value = change.get('value', {})
        
        # フィールド変更を検出
        print(f"フィールド変更検出: field={field}, value={json.dumps(value, indent=2, ensure_ascii=False)}")
        
        # messagesフィールド以外はスキップ
        if field != 'messages':
            print(f"messagesフィールド以外のため処理スキップ: {field}")
            continue
            
        # メッセージ情報を取得
        sender_id = value.get('sender', {}).get('id')
        recipient_id = value.get('recipient', {}).get('id')  # 受信者ID（通常はページID）
        message = value.get('message', {})
        message_text = message.get('text', '')
        
        # メッセージがない場合はスキップ
        if not message_text:
            print("テキストのないメッセージ（画像など）はスキップします")
            continue
            
        # エコーメッセージのチェック
        if message.get('is_echo') == True:
            print(f"フィールドベースのエコーメッセージを検出しました。処理をスキップします: {message_text[:50]}...")
            continue
        
        # 送信済みメッセージのチェック（ループ防止）
        if SentMessage.has_recent_message(sender_id, sender_id):
            print(f"24時間以内に自動返信を送信済みの相手からのメッセージです。処理をスキップします。sender_id={sender_id}, recipient_id={recipient_id}")
            continue
            
        # 有効なメッセージ変更を追加
        valid_changes.append((change, sender_id, message_text))
    
    # 有効なメッセージ変更がない場合は終了
    if not valid_changes:
        print("処理対象のメッセージ変更がありません")
        return
        
    # ユーザー情報を取得
    user = get_user_by_ids(page_id)
    if not user:
        print("フィールドベースのwebhookで有効なユーザーが見つかりません")
        return
    
    # ユーザーの自動返信が有効かチェック
    if not user.autoreply_enabled:
        print(f"ユーザーID{user.id}の自動返信が無効です")
        return
        
    # 有効なメッセージ変更に対して処理を実行
    for change, sender_id, message_text in valid_changes:
        print(f"フィールドベースで受信したメッセージ: {message_text}, 送信者: {sender_id}")
        
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
            profile_url = f"https://{request.host}{user.get_public_url()}"
            reply_message = template.replace('{profile_url}', profile_url)
            
            # Instagram API with Instagram Login対応 - Instagram Tokenを優先して使用
            access_token = user.instagram_token
            if not access_token:
                print(f"ユーザーID{user.id}のInstagramトークンが設定されていません。Facebookトークンを試します。")
                access_token = user.facebook_token
            
            if not access_token:
                print(f"ユーザーID{user.id}のアクセストークンが設定されていません")
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

def send_instagram_reply(access_token, recipient_id, message_text, max_retries=1):
    """Instagramに直接メッセージを送信する"""
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            # Instagram APIエンドポイント
            url = "https://graph.instagram.com/v22.0/me/messages"
            
            # リクエストデータの詳細ログ
            print(f"Instagram APIリクエスト情報: URL={url}, recipient_id(instagram_user_id)={recipient_id}, トークン長さ={len(access_token)}")
            
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
            
            response = requests.post(url, headers=headers, params=params, json=payload, timeout=10)
            
            # レスポンスコンテンツを取得
            response_content = response.text
            
            # エラーレスポンスの詳細ログ
            if response.status_code != 200:
                print(f"Instagram API エラー詳細:")
                print(f"- ステータスコード: {response.status_code}")
                print(f"- レスポンス内容: {response_content}")
                print(f"- リクエストURL: {url}")
                print(f"- リクエストヘッダー: {headers}")
                print(f"- リクエストパラメータ: access_token=***（セキュリティのため非表示）")
                
                # エラーレスポンスをJSONとして解析
                try:
                    error_json = json.loads(response_content)
                    if "error" in error_json:
                        error_obj = error_json["error"]
                        print(f"- エラータイプ: {error_obj.get('type')}")
                        print(f"- エラーコード: {error_obj.get('code')}")
                        print(f"- エラーサブコード: {error_obj.get('error_subcode')}")
                        print(f"- エラーメッセージ: {error_obj.get('message')}")
                except:
                    print("- JSONエラー解析に失敗しました")
            
            print(f"Instagram API応答: ステータスコード {response.status_code}, レスポンス {response_content}")
            
            if response.status_code == 200:
                print("Instagram返信送信成功")
                
                # メッセージIDを抽出してデータベースに記録
                try:
                    response_data = json.loads(response_content)
                    message_id = response_data.get('message_id')
                    
                    # インスタンスのページIDと受信者IDを使って記録
                    # 注意: Instagram APIではリクエスト時のrecipient_idが受信者となり、
                    # page_idが送信者となるため、このように記録します
                    # 呼び出し元で sender_id <-> recipient_id の関係を認識して処理する
                    
                    # 送信したメッセージを記録
                    sent_message = SentMessage(
                        message_id=message_id,
                        sender_id=recipient_id,  # メッセージの受信者IDをSentMessageの送信者IDとして記録
                        recipient_id=recipient_id # 同じIDを受信者としても記録（フィルタリングの目的のため）
                    )
                    db.session.add(sent_message)
                    db.session.commit()
                    
                    print(f"メッセージ送信記録を作成しました: message_id={message_id}, sender_id={recipient_id}, recipient_id={recipient_id}")
                    
                    # 24時間以上経過した古いメッセージ記録をクリーンアップ
                    deleted_count = SentMessage.cleanup_expired()
                    if deleted_count > 0:
                        print(f"期限切れのメッセージ記録 {deleted_count}件 を削除しました")
                except Exception as e:
                    print(f"メッセージ記録の作成中にエラー発生: {str(e)}")
                    print(traceback.format_exc())
                    # メッセージ記録に失敗しても、メッセージ自体は送信されているため成功とみなす
                
                return True
            elif retry_count < max_retries:
                # リトライする場合
                retry_count += 1
                print(f"Instagram返信送信失敗。リトライします ({retry_count}/{max_retries})...")
                time.sleep(1)  # 1秒待機してからリトライ
            else:
                # リトライ回数を超えた場合は失敗として返す
                print(f"Instagram返信送信失敗: ステータスコード {response.status_code}, レスポンス {response_content}")
                print(f"最大リトライ回数 ({max_retries}) に達しました。処理を中止します。")
                return False
            
        except Exception as e:
            if retry_count < max_retries:
                # リトライする場合
                retry_count += 1
                print(f"Instagram返信送信中に例外が発生しました: {str(e)}。リトライします ({retry_count}/{max_retries})...")
                print(traceback.format_exc())
                time.sleep(1)  # 1秒待機してからリトライ
            else:
                # リトライ回数を超えた場合は失敗として返す
                print(f"Instagram返信送信中に例外が発生しました: {str(e)}")
                print(traceback.format_exc())
                print(f"最大リトライ回数 ({max_retries}) に達しました。処理を中止します。")
                return False
    
    return False  # ここには到達しないはずだが、念のため 