import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session, jsonify, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db, csrf
from app.models.user import User
from app.models.spot import Spot
from app.models.import_progress import ImportProgress
from app.utils.s3_utils import upload_file_to_s3, delete_file_from_s3
import uuid
import requests
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import traceback
from app.services.google_photos import get_google_photos_by_place_id

bp = Blueprint('profile', __name__)

# 許可するファイル拡張子
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/mypage')
@login_required
def mypage():
    """マイページ"""
    # ページネーションのためのページ番号を取得（デフォルトは1ページ目）
    page = request.args.get('page', 1, type=int)
    # 1ページあたりの表示件数
    per_page = 10
    
    # ユーザーのスポットをクエリし、ページネーション
    spots_pagination = Spot.query.filter_by(user_id=current_user.id)\
        .order_by(Spot.is_active.desc(), Spot.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    # APIリクエストの場合はJSONレスポンスを返す
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # スポットデータをJSON形式に変換
        spots_data = []
        for spot in spots_pagination.items:
            # ユーザーがアップロードした写真
            user_photos = [p for p in spot.photos if not p.is_google_photo]
            user_photo_list = [{'photo_url': p.photo_url} for p in user_photos]

            # Google PhotosをPlace ID経由で取得
            google_photo_list = []
            if spot.google_place_id:
                try:
                    google_photo_urls = get_google_photos_by_place_id(spot.google_place_id)
                    google_photo_list = [{'photo_url': url} for url in google_photo_urls]
                except Exception as e:
                    print(f"Google Photos取得エラー (spot_id: {spot.id}): {e}")
                    google_photo_list = []
            
            # ユーザー写真とGoogle写真を結合
            all_photos = user_photo_list + google_photo_list
            
            spot_dict = {
                'id': spot.id,
                'name': spot.name,
                'location': spot.location,
                'summary_location': spot.summary_location,
                'category': spot.category,
                'is_active': spot.is_active,
                'rating': spot.rating,
                'photo_url': all_photos[0]['photo_url'] if all_photos else None
            }
            spots_data.append(spot_dict)
        
        # ページネーション情報を含めてJSONを返す
        return jsonify({
            'spots': spots_data,
            'has_next': spots_pagination.has_next,
            'has_prev': spots_pagination.has_prev,
            'next_page': spots_pagination.next_num,
            'prev_page': spots_pagination.prev_num,
            'total_pages': spots_pagination.pages,
            'current_page': spots_pagination.page
        })
    
    # 通常のリクエストの場合 - プロフィールページと同じようにスポットデータを処理
    spots_with_photos = []
    for spot in spots_pagination.items:
        # ユーザーがアップロードした写真
        user_photos = [p for p in spot.photos if not p.is_google_photo]
        user_photo_list = [{'photo_url': p.photo_url} for p in user_photos]

        # Google PhotosをPlace ID経由で取得
        google_photo_list = []
        if spot.google_place_id:
            try:
                google_photo_urls = get_google_photos_by_place_id(spot.google_place_id)
                google_photo_list = [{'photo_url': url} for url in google_photo_urls]
            except Exception as e:
                print(f"Google Photos取得エラー (spot_id: {spot.id}): {e}")
                google_photo_list = []
        
        # ユーザー写真とGoogle写真を結合
        all_photos = user_photo_list + google_photo_list
        
        # spotオブジェクトに統合された写真リストを追加
        spot.unified_photos = all_photos
        spots_with_photos.append(spot)
    
    # 通常のリクエストの場合はテンプレートをレンダリング
    return render_template('mypage.html', 
                          user=current_user, 
                          spots=spots_with_photos,
                          pagination=spots_pagination)

@bp.route('/update-spots-heading', methods=['POST'])
@login_required
def update_spots_heading():
    """スポット見出しの更新"""
    spots_heading = request.form.get('spots_heading', '').strip()
    
    # 入力値の検証
    if not spots_heading:
        flash('見出しを入力してください', 'danger')
        return redirect(url_for('profile.mypage'))
    
    if len(spots_heading) > 50:
        flash('見出しは50文字以内で入力してください', 'danger')
        return redirect(url_for('profile.mypage'))
    
    # 見出しを更新
    current_user.spots_heading = spots_heading
    db.session.commit()
    
    flash('見出しを更新しました', 'success')
    return redirect(url_for('profile.mypage'))

@bp.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """プロフィール編集ページ"""
    if request.method == 'POST':
        username = request.form.get('username')
        bio = request.form.get('bio')
        
        # ユーザー名の重複チェック（自分以外）
        if username != current_user.username and User.query.filter_by(username=username).first():
            flash('このユーザー名は既に使用されています。', 'danger')
            return render_template('edit_profile.html', user=current_user)
        
        # プロフィール画像のアップロード処理
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '' and allowed_file(file.filename):
                # S3が有効かチェック
                if current_app.config.get('USE_S3', False):
                    # S3にアップロード (profile_imgフォルダに保存)
                    photo_url = upload_file_to_s3(file, folder='profile_img')
                    
                    # アップロードに成功した場合のみ処理
                    if photo_url:
                        current_user.profile_pic_url = photo_url
                    else:
                        flash('プロフィール画像のアップロードに失敗しました。', 'danger')
                else:
                    # ローカルに保存
                    filename = secure_filename(file.filename)
                    # ユーザーIDをファイル名に含める
                    filename = f"{current_user.id}_{filename}"
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    
                    # データベースに保存するパスは相対パス
                    relative_path = os.path.join('uploads', filename)
                    current_user.profile_pic_url = relative_path
        
        # ユーザー情報の更新
        current_user.username = username
        current_user.bio = bio
        db.session.commit()
        
        flash('プロフィールが更新されました。', 'success')
        return redirect(url_for('profile.mypage'))
    
    return render_template('edit_profile.html', user=current_user)

@bp.route('/settings')
@login_required
def settings():
    """設定ページ"""
    return render_template('settings.html')

@bp.route('/settings/account')
@login_required
def account_settings():
    """アカウント設定ページ"""
    return render_template('account_settings.html')

@bp.route('/settings/sns')
@login_required
def sns_settings():
    """SNS連携設定ページ"""
    # Instagramの連携状態を確認
    instagram_connected = False
    if hasattr(current_user, 'instagram_token') and current_user.instagram_token:
        instagram_connected = True
    
    return render_template('sns.html', instagram_connected=instagram_connected)

@bp.route('/connect/instagram')
@login_required
def connect_instagram():
    """Instagramとの連携を開始"""
    # Instagram Business Loginの認証フローを開始
    # クライアントIDとリダイレクトURIを設定
    client_id = current_app.config.get('INSTAGRAM_CLIENT_ID')
    
    # デバッグ情報を表示
    print(f"Instagram Client ID: {client_id}")
    print(f"Instagram Client Secret: {current_app.config.get('INSTAGRAM_CLIENT_SECRET')}")
    
    # リダイレクトURIを設定
    redirect_uri = current_app.config.get('INSTAGRAM_REDIRECT_URI')
    
    # 環境変数が設定されていない場合は、リクエストから生成
    if not redirect_uri:
        host = request.host
        if ':' in host:
            # ポート番号が含まれている場合は削除して8085を使用
            host_without_port = host.split(':')[0]
            # localhostと127.0.0.1を区別（Meta Developersでは別のURIとして扱われる）
            if host_without_port == '127.0.0.1':
                redirect_uri = f"https://127.0.0.1:8085/instagram/callback"
            else:
                redirect_uri = f"https://localhost:8085/instagram/callback"
        else:
            # ポート番号がない場合（本番環境など）
            redirect_uri = f"https://{host}/instagram/callback"
    
    print(f"Redirect URI: {redirect_uri}")
    
    if not client_id:
        flash('Instagram連携の設定が完了していません。管理者にお問い合わせください。', 'danger')
        return redirect(url_for('profile.sns_settings'))
    
    # CSRF対策のstateパラメータを生成
    state = str(uuid.uuid4())
    session['instagram_auth_state'] = state
    
    # 2024年最新の有効なスコープ - Instagram API with Instagram Login対応
    scope = "instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments,instagram_business_content_publish,instagram_business_manage_insights"
    
    # Instagram認証URLを生成 - Facebook連携を必須としない設定
    # enable_fb_login=0は古いAPI向けのパラメータ、force_authentication=1は常に認証を要求する設定
    # force_direct_instagramを追加して直接Instagram認証を強制
    auth_url = f"https://www.instagram.com/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}&response_type=code&state={state}&enable_fb_login=0&force_authentication=1&force_direct_instagram=true"
    
    print(f"Auth URL: {auth_url}")
    
    # Instagram認証ページにリダイレクト
    return redirect(auth_url)

def configure_instagram_webhook(instagram_business_id, instagram_token):
    """Instagramビジネスアカウントに直接Webhookを設定（Facebook不要）"""
    try:
        webhook_url = request.host_url.rstrip('/') + '/webhook/instagram'
        verify_token = current_app.config.get('INSTAGRAM_WEBHOOK_VERIFY_TOKEN')
        
        print(f"Setting up webhook for Instagram Business ID: {instagram_business_id}")
        print(f"Webhook URL: {webhook_url}")
        print(f"Verify Token: {verify_token}")
        
        # Instagram APIではユーザーレベルのサブスクリプションのみが必要
        user_subscription_url = f"https://graph.instagram.com/v22.0/{instagram_business_id}/subscribed_apps"
        user_params = {
            'access_token': instagram_token,
            'subscribed_fields': 'messages'
        }
        
        print(f"Setting up user-level subscription: {user_subscription_url}")
        print(f"User subscription params: {user_params}")
        user_response = requests.post(user_subscription_url, params=user_params)
        user_data = user_response.json()
        print(f"User subscription response status: {user_response.status_code}")
        print(f"User subscription response: {user_data}")
        
        user_success = user_response.status_code == 200 and user_data.get('success', False)
        
        if user_success:
            return True, "Webhookサブスクリプションの設定に成功しました"
        else:
            return False, "Webhookサブスクリプションの設定に失敗しました"
    
    except Exception as e:
        print(f"Webhook設定中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        return False, f"Webhook設定中にエラー: {str(e)}"

@bp.route('/instagram/callback')
@login_required
def instagram_callback():
    """Instagram認証後のコールバック処理"""
    # 認証コードを取得
    code = request.args.get('code')
    error = request.args.get('error')
    error_reason = request.args.get('error_reason')
    state = request.args.get('state')
    
    # エラーチェック
    if error:
        flash(f'Instagram連携に失敗しました: {error_reason}', 'danger')
        return redirect(url_for('profile.sns_settings'))
    
    if not code:
        flash('認証コードが取得できませんでした。', 'danger')
        return redirect(url_for('profile.sns_settings'))
    
    # CSRF対策の状態チェック
    if not session.get('instagram_auth_state') or session.get('instagram_auth_state') != state:
        flash('セキュリティ上の問題が発生しました。もう一度お試しください。', 'danger')
        return redirect(url_for('profile.sns_settings'))
    
    # セッションから状態を削除
    session.pop('instagram_auth_state', None)
    
    # アクセストークンを取得するためのリクエストを準備
    client_id = current_app.config.get('INSTAGRAM_CLIENT_ID')
    client_secret = current_app.config.get('INSTAGRAM_CLIENT_SECRET')
    
    # リダイレクトURIを設定
    redirect_uri = current_app.config.get('INSTAGRAM_REDIRECT_URI')
    
    # 環境変数が設定されていない場合は、リクエストから生成
    if not redirect_uri:
        host = request.host
        if ':' in host:
            # ポート番号が含まれている場合は削除して8085を使用
            host_without_port = host.split(':')[0]
            # localhostと127.0.0.1を区別（Meta Developersでは別のURIとして扱われる）
            if host_without_port == '127.0.0.1':
                redirect_uri = f"https://127.0.0.1:8085/instagram/callback"
            else:
                redirect_uri = f"https://localhost:8085/instagram/callback"
        else:
            # ポート番号がない場合（本番環境など）
            redirect_uri = f"https://{host}/instagram/callback"
    
    print(f"Callback - Redirect URI: {redirect_uri}")
    
    if not client_id or not client_secret:
        flash('Instagram連携の設定が完了していません。管理者にお問い合わせください。', 'danger')
        return redirect(url_for('profile.sns_settings'))
    
    try:
        # アクセストークンを取得（POSTリクエスト）
        token_url = 'https://api.instagram.com/oauth/access_token'
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'code': code
        }
        
        # POSTリクエストを送信
        response = requests.post(token_url, data=payload)
        token_data = response.json()
        
        print(f"Token response: {token_data}")
        
        if 'error_type' in token_data or 'error' in token_data:
            error_message = token_data.get('error_message', token_data.get('error_description', '不明なエラー'))
            flash(f'アクセストークンの取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # 短期アクセストークンとInstagramユーザーIDを取得
        short_lived_token = token_data.get('access_token')
        instagram_user_id = token_data.get('user_id')
        
        if not short_lived_token or not instagram_user_id:
            flash('アクセストークンまたはユーザーIDの取得に失敗しました。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        print(f"Got short-lived token and user ID: {instagram_user_id}")
        
        # 長期アクセストークンに交換（60日間有効）
        graph_url = f"https://graph.instagram.com/v22.0/access_token?grant_type=ig_exchange_token&client_secret={client_secret}&access_token={short_lived_token}"
        response = requests.get(graph_url)
        long_lived_data = response.json()
        
        print(f"Long-lived token response: {long_lived_data}")
        
        if 'error' in long_lived_data:
            error_message = long_lived_data.get('error', {}).get('message', '不明なエラー')
            flash(f'長期アクセストークンの取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        long_lived_token = long_lived_data.get('access_token')
        expires_in = long_lived_data.get('expires_in', 5184000)  # デフォルトは60日（5184000秒）
        
        # ユーザー情報を取得 - 明示的にuser_idフィールドを要求
        user_info_url = f"https://graph.instagram.com/v22.0/me?fields=username,account_type,user_id,id&access_token={long_lived_token}"
        response = requests.get(user_info_url)
        user_info = response.json()
        
        print(f"User info response: {user_info}")
        
        if 'error' in user_info:
            error_message = user_info.get('error', {}).get('message', '不明なエラー')
            flash(f'ユーザー情報の取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        instagram_username = user_info.get('username')
        account_type = user_info.get('account_type', 'unknown')
        
        # 2種類のIDを取得
        instagram_business_id = user_info.get('id')  # 既存の取得していたID (API用)
        messaging_user_id = user_info.get('user_id')  # 新しく取得するID (メッセージング用)
        
        print(f"取得したID情報 - Business ID (id): {instagram_business_id}, Messaging ID (user_id): {messaging_user_id}")
        
        # メッセージング用IDが取得できない場合のフォールバック処理
        if not messaging_user_id:
            print(f"Warning: user_id was not returned from the API. Trying an alternative method.")
            # 代替方法でuser_idを取得を試みる
            try:
                alt_user_info_url = f"https://graph.instagram.com/v22.0/me?fields=id,user_id&access_token={long_lived_token}"
                alt_response = requests.get(alt_user_info_url)
                alt_user_info = alt_response.json()
                print(f"Alternative user info response: {alt_user_info}")
                messaging_user_id = alt_user_info.get('user_id')
                
                if not messaging_user_id:
                    print(f"Warning: Still could not retrieve user_id. This may cause issues with messaging.")
            except Exception as e:
                print(f"Error in alternative user_id retrieval: {str(e)}")
        
        # アカウントタイプをチェック（プロアカウントかどうか）
        if account_type not in ['BUSINESS', 'MEDIA_CREATOR']:
            flash(f'Instagram連携にはプロアカウント（ビジネスまたはクリエイター）が必要です。現在のアカウントタイプ: {account_type}', 'warning')
            # プロアカウントでない場合でも、一応情報は保存する
        else:
            # プロアカウントの場合は追加設定を行う
            try:
                # ビジネスアカウント情報を取得
                print(f"ビジネスアカウント情報の取得を開始（アカウントタイプ: {account_type}）")
                
                # Business IDがすでに取得できている場合は、それを使用
                if instagram_business_id:
                    print(f"API用 Instagram Business ID (id): {instagram_business_id}")
                else:
                    # バックアップとして通常のIDフェッチを試みる
                    # Instagramのユーザー情報を取得
                    instagram_id_url = f"https://graph.instagram.com/v22.0/me?fields=id,username&access_token={long_lived_token}"
                    ig_response = requests.get(instagram_id_url)
                    ig_info = ig_response.json()
                    
                    print(f"Instagram ID情報レスポンス: {ig_info}")
                    
                    if 'id' in ig_info:
                        # APIのIDを取得
                        instagram_business_id = ig_info['id']
                        print(f"Instagram Business ID: {instagram_business_id}")
                
                # メッセージング用IDの確認
                if messaging_user_id:
                    print(f"メッセージング用 Instagram User ID (user_id): {messaging_user_id}")
                else:
                    print(f"警告: メッセージング用IDを取得できませんでした。DMの送受信が機能しない可能性があります。")
                
                # ビジネスアカウントIDを保存
                if instagram_business_id:
                    current_user.instagram_business_id = instagram_business_id
                    print(f"Instagram Business ID (API用)を保存: {instagram_business_id}")
                
                # ユーザー名を取得
                ig_username = instagram_username or user_info.get('username', '')
                
                # データベースに保存
                if ig_username:
                    current_user.instagram_username = ig_username
                
                print(f"Instagram連携が完了しました（Business ID: {instagram_business_id}, User ID: {messaging_user_id}, ユーザー名: {ig_username}）")
                flash('Instagram連携が完了しました！', 'success')
            except Exception as e:
                print(f"ビジネスアカウント情報取得中にエラー: {str(e)}")
                print(traceback.format_exc())
                flash('Instagram連携中にエラーが発生しました。', 'warning')
        
        # ユーザーモデルに保存
        current_user.instagram_token = long_lived_token
        current_user.instagram_user_id = messaging_user_id  # メッセージング用ID
        current_user.instagram_username = instagram_username
        current_user.instagram_business_id = instagram_business_id  # API用ID
        current_user.instagram_connected_at = datetime.utcnow()
        db.session.commit()
        
        # Webhookの登録処理を追加 - Business IDを使用（従来通り）
        if instagram_business_id:
            webhook_success, webhook_message = configure_instagram_webhook(
                instagram_business_id,  # API用ID (従来のまま)
                long_lived_token
            )
            if webhook_success:
                print(f"Webhook登録成功: {webhook_message}")
                flash('Instagram連携とwebhook登録が完了しました！', 'success')
            else:
                print(f"Webhook登録失敗: {webhook_message}")
                flash('Instagram連携は完了しましたが、webhook登録に失敗しました。', 'warning')
        else:
            flash('Instagram連携が完了しました！', 'success')
    except Exception as e:
        print(f"Instagram連携中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        flash(f'Instagram連携中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('profile.sns_settings'))

# Meta APIを使用してアクセストークンを失効させる
def revoke_meta_token(access_token, app_id=None):
    """
    Meta APIを使用してアクセストークンを失効させる
    
    Args:
        access_token (str): 失効させるアクセストークン
        app_id (str, optional): アプリID（デバッグトークンに使用）
    
    Returns:
        bool: 成功したかどうか
    """
    if not access_token:
        return False
    
    try:
        # アプリIDが指定されていない場合は設定から取得
        if not app_id:
            app_id = current_app.config.get('INSTAGRAM_CLIENT_ID')
        
        # トークンの失効リクエスト
        revoke_url = f"https://graph.facebook.com/v22.0/me/permissions"
        params = {
            'access_token': access_token
        }
        
        # APIリクエストとレスポンスをログに記録
        current_app.logger.info(f"Revoking Meta token - URL: {revoke_url}, Params: {json.dumps({'access_token': '[REDACTED]'})}")
        
        response = requests.delete(revoke_url, params=params)
        
        # レスポンスの詳細をログに記録（トークン情報はマスク）
        current_app.logger.info(f"Meta token revocation response - Status: {response.status_code}, Body: {response.text}")
        
        # 成功レスポンスは {"success": true} が返ってくる
        if response.status_code == 200:
            result = response.json()
            return result.get('success', False)
        
        # エラーレスポンスの場合はログに記録
        current_app.logger.error(f"Meta token revocation failed: {response.text}")
        return False
    
    except Exception as e:
        current_app.logger.exception(f"Error revoking Meta token: {str(e)}")
        return False

# Meta Webhookサブスクリプションを解除する
def unsubscribe_webhook(app_id, app_secret, subscription_id=None):
    """
    Meta Webhookサブスクリプションを解除する（アプリレベル）
    
    Args:
        app_id (str): アプリID
        app_secret (str): アプリシークレット
        subscription_id (str, optional): 特定のサブスクリプションIDを削除する場合
    
    Returns:
        bool: 成功したかどうか
    """
    try:
        # アプリアクセストークンを生成
        app_access_token = f"{app_id}|{app_secret}"
        
        # すべてのWebhookサブスクリプションを削除
        webhook_url = f"https://graph.facebook.com/v22.0/{app_id}/subscriptions"
        
        if subscription_id:
            # 特定のサブスクリプションのみを削除
            params = {
                'access_token': app_access_token,
                'object': 'instagram',
                'callback_url': '',  # 空のコールバックURLは削除を意味する
                'subscription_id': subscription_id
            }
            # アクセストークンを隠してログ記録
            log_params = params.copy()
            log_params['access_token'] = '[REDACTED]'
            current_app.logger.info(f"Unsubscribing specific webhook - URL: {webhook_url}, Params: {json.dumps(log_params)}")
            
            response = requests.delete(webhook_url, params=params)
        else:
            # すべてのサブスクリプションを削除
            params = {
                'access_token': app_access_token,
                'object': 'instagram'
            }
            # アクセストークンを隠してログ記録
            log_params = params.copy()
            log_params['access_token'] = '[REDACTED]'
            current_app.logger.info(f"Unsubscribing all webhooks - URL: {webhook_url}, Params: {json.dumps(log_params)}")
            
            response = requests.delete(webhook_url, params=params)
        
        # レスポンスをログに記録
        current_app.logger.info(f"Webhook unsubscription response - Status: {response.status_code}, Body: {response.text}")
        
        # 成功レスポンスは {"success": true} が返ってくる
        if response.status_code == 200:
            result = response.json()
            return result.get('success', False)
        
        # エラーレスポンスの場合はログに記録
        current_app.logger.error(f"Webhook unsubscription failed: {response.text}")
        return False
    
    except Exception as e:
        current_app.logger.exception(f"Error unsubscribing webhook: {str(e)}")
        return False

# Instagram Webhookサブスクリプションを解除する（ユーザーレベル）
def unsubscribe_instagram_webhook(instagram_business_id, instagram_token):
    """
    Instagram Webhookサブスクリプションを解除する（ユーザーレベル）
    
    Args:
        instagram_business_id (str): Instagram Business ID
        instagram_token (str): Instagram アクセストークン
    
    Returns:
        bool: 成功したかどうか
    """
    try:
        if not instagram_business_id or not instagram_token:
            current_app.logger.warning("Instagram Business IDまたはアクセストークンが不足しています")
            return False
            
        # ユーザーレベルのサブスクリプションを解除
        user_subscription_url = f"https://graph.instagram.com/v22.0/{instagram_business_id}/subscribed_apps"
        params = {
            'access_token': instagram_token
        }
        
        # ログ記録（アクセストークンは隠す）
        current_app.logger.info(f"Unsubscribing Instagram webhook - Business ID: {instagram_business_id}, URL: {user_subscription_url}")
        
        response = requests.delete(user_subscription_url, params=params)
        
        # レスポンスをログに記録
        current_app.logger.info(f"Instagram webhook unsubscription response - Status: {response.status_code}, Body: {response.text}")
        
        # 成功レスポンスは {"success": true} が返ってくる
        if response.status_code == 200:
            result = response.json()
            return result.get('success', False)
        
        # エラーレスポンスの場合はログに記録
        current_app.logger.error(f"Instagram webhook unsubscription failed: {response.text}")
        return False
    
    except Exception as e:
        current_app.logger.exception(f"Error unsubscribing Instagram webhook: {str(e)}")
        return False

@bp.route('/disconnect/instagram', methods=['POST'])
@login_required
def disconnect_instagram():
    """Instagram連携を解除"""
    # CSRFトークンの検証（Flask-WTF内でチェック）
    
    try:
        # アクセストークンを失効させて、アプリ連携を解除
        access_token = current_user.instagram_token
        if access_token:
            revoke_meta_token(access_token)
        
        # Instagram Webhookサブスクリプションを解除
        if current_user.instagram_business_id and current_user.instagram_token:
            unsubscribe_instagram_webhook(current_user.instagram_business_id, current_user.instagram_token)
        
        # Instagram連携情報をクリア
        current_user.instagram_token = None
        current_user.instagram_user_id = None
        current_user.instagram_username = None
        current_user.instagram_business_id = None
        current_user.instagram_connected_at = None
        current_user.webhook_subscription_id = None
        
        # Facebook連携情報もクリア（依存関係のため）
        if current_user.facebook_token:
            try:
                # Facebookページのwebhookサブスクリプション解除
                if current_user.facebook_page_id:
                    unsubscribe_page_webhook(current_user.facebook_page_id, current_user.facebook_token)
            except Exception as fb_error:
                print(f"Facebook連携解除中に例外が発生: {str(fb_error)}")
        
        # Facebook連携情報をクリア
        current_user.facebook_token = None
        current_user.facebook_page_id = None
        current_user.facebook_connected_at = None
        
        # 自動返信設定も無効化
        current_user.autoreply_enabled = False
        
        # 変更をデータベースに保存
        db.session.commit()
        
        flash('Instagram連携を解除しました', 'success')
    except Exception as e:
        print(f"Instagram連携解除中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        flash(f'Instagram連携解除中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('profile.sns_settings'))



@bp.route('/import')
@login_required
def import_management():
    """インポート管理ページ"""
    # Instagram連携状態を確認
    is_instagram_connected = current_user.instagram_token is not None
    
    return render_template('import.html', 
                          is_instagram_connected=is_instagram_connected,
                          instagram_username=current_user.instagram_username)

@bp.route('/autoreply')
@login_required
def autoreply_settings():
    """自動返信設定ページ"""
    # ログインユーザーを明示的に取得
    user_id = current_user.id
    print(f"Autoreply settings for user ID: {user_id}")
    
    # 念のため、データベースから直接ユーザーを取得
    user = User.query.get(user_id)
    if not user:
        flash('ユーザー情報が取得できませんでした', 'danger')
        return redirect(url_for('main.index'))
    
    print(f"Loaded user for autoreply: {user.id} - {user.username}")
    print(f"Facebook connection status: Token: {'Yes' if user.facebook_token else 'No'}, Page ID: {user.facebook_page_id}")
    
    return render_template('autoreply.html', title='自動返信設定')

@bp.route('/connect/facebook')
@login_required
def connect_facebook():
    """DM自動返信機能の有効化（Facebookとの連携）"""
    # CSRFトークンを設定
    session['facebook_csrf_token'] = str(uuid.uuid4())
    
    # Facebook認証URLを構築
    app_id = current_app.config.get('FACEBOOK_APP_ID')
    redirect_uri = url_for('profile.facebook_callback', _external=True)
    print(f"Facebook App ID: {app_id}")
    print(f"Facebook App Secret: {current_app.config.get('FACEBOOK_APP_SECRET')}")
    print(f"Redirect URI: {redirect_uri}")
    
    # 認証スコープを設定
    scopes = [
        'pages_show_list', 
        'pages_manage_metadata', 
        'pages_read_engagement',
        'pages_manage_posts',
        'pages_messaging',
        'instagram_manage_messages',  # Instagram DMの管理権限を追加
        'business_management'  # ビジネス管理のスコープを追加
    ]
    
    auth_url = f"https://www.facebook.com/v22.0/dialog/oauth?client_id={app_id}&redirect_uri={redirect_uri}&state={session['facebook_csrf_token']}&scope={','.join(scopes)}"
    print(f"Auth URL: {auth_url}")
    
    # Facebook認証ページにリダイレクト
    return redirect(auth_url)

@bp.route('/facebook/callback')
@login_required
def facebook_callback():
    """Facebook認証後のコールバック処理（DM自動返信機能の有効化）"""
    # 認証コードを取得
    code = request.args.get('code')
    error = request.args.get('error')
    error_reason = request.args.get('error_reason')
    state = request.args.get('state')
    
    # エラーチェック
    if error:
        flash(f'DM自動返信機能の有効化に失敗しました: {error_reason}', 'danger')
        return redirect(url_for('profile.autoreply_settings'))
    
    if not code:
        flash('認証コードが取得できませんでした。', 'danger')
        return redirect(url_for('profile.autoreply_settings'))
    
    # CSRF対策の状態チェック
    if state != session.get('facebook_csrf_token'):
        flash('セキュリティ上の問題が発生しました。もう一度お試しください。', 'danger')
        return redirect(url_for('profile.autoreply_settings'))
    
    # セッションから状態を削除
    session.pop('facebook_csrf_token', None)
    
    # アクセストークンを取得するためのリクエストを準備
    client_id = current_app.config.get('FACEBOOK_APP_ID')
    client_secret = current_app.config.get('FACEBOOK_APP_SECRET')
    
    # リダイレクトURIを設定
    redirect_uri = request.host_url.rstrip('/') + url_for('profile.facebook_callback')
    
    print(f"Callback - Redirect URI: {redirect_uri}")
    
    if not client_id or not client_secret:
        flash('Facebook連携の設定が完了していません。管理者にお問い合わせください。', 'danger')
        return redirect(url_for('profile.autoreply_settings'))
    
    try:
        # アクセストークンを取得（POSTリクエスト）
        token_url = 'https://graph.facebook.com/v22.0/oauth/access_token'
        params = {
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'code': code
        }
        
        # GETリクエストを送信
        response = requests.get(token_url, params=params)
        token_data = response.json()
        
        print(f"Token response: {token_data}")
        
        if 'error' in token_data:
            error_message = token_data.get('error', {}).get('message', '不明なエラー')
            flash(f'アクセストークンの取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        # アクセストークンを取得
        access_token = token_data.get('access_token')
        
        if not access_token:
            flash('アクセストークンの取得に失敗しました。', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        # ユーザー情報を取得
        user_info_url = f"https://graph.facebook.com/v22.0/me?fields=id,name&access_token={access_token}"
        
        # appsecret_proofを生成（HMAC-SHA256ハッシュ）
        appsecret_proof = hmac.new(
            client_secret.encode('utf-8'),
            access_token.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # appsecret_proofをパラメータに追加
        user_info_url = f"{user_info_url}&appsecret_proof={appsecret_proof}"
        
        response = requests.get(user_info_url)
        user_info = response.json()
        
        print(f"User info response: {user_info}")
        
        if 'error' in user_info:
            error_message = user_info.get('error', {}).get('message', '不明なエラー')
            flash(f'ユーザー情報の取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        facebook_user_id = user_info.get('id')
        
        print(f"Facebook User ID: {facebook_user_id}")
        
        # ページ一覧を取得
        pages_url = f"https://graph.facebook.com/v22.0/{facebook_user_id}/accounts?access_token={access_token}&appsecret_proof={appsecret_proof}"
        print(f"Pages URL: {pages_url}")
        
        # リクエストヘッダーを設定
        headers = {
            'User-Agent': 'Trip App/1.0',
            'Content-Type': 'application/json'
        }
        
        # APIリクエストを送信
        response = requests.get(pages_url, headers=headers)
        print(f"Pages API Status Code: {response.status_code}")
        print(f"Pages API Response Headers: {response.headers}")
        
        try:
            pages_data = response.json()
            print(f"Pages response (full): {pages_data}")
        except Exception as e:
            print(f"Error parsing pages response: {str(e)}")
            print(f"Raw response: {response.text}")
            pages_data = {}
        
        # ページデータが空の場合はエラーメッセージを表示
        if not pages_data.get('data'):
            flash('接続可能なFacebookページが見つかりませんでした。Instagramプロアカウントと接続されているか確認してください。', 'warning')
            return redirect(url_for('profile.autoreply_settings'))
        
        if 'error' in pages_data:
            error_message = pages_data.get('error', {}).get('message', '不明なエラー')
            error_code = pages_data.get('error', {}).get('code', 'unknown')
            error_type = pages_data.get('error', {}).get('type', 'unknown')
            print(f"Pages API Error: {error_type} ({error_code}) - {error_message}")
            flash(f'ページ情報の取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        pages = pages_data.get('data', [])
        
        if not pages:
            flash('接続可能なFacebookページが見つかりませんでした。Instagramプロアカウントとして設定されているか確認してください。', 'warning')
            return redirect(url_for('profile.autoreply_settings'))
        
        # 最初のページを使用
        page = pages[0]
        page_id = page.get('id')
        page_name = page.get('name')
        page_access_token = page.get('access_token')
        
        # ページトークン用のappsecret_proof生成
        page_appsecret_proof = hmac.new(
            client_secret.encode('utf-8'),
            page_access_token.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # ページトークンを長期トークンに変換
        long_lived_url = f"https://graph.facebook.com/v22.0/oauth/access_token?grant_type=fb_exchange_token&client_id={client_id}&client_secret={client_secret}&fb_exchange_token={page_access_token}"
        response = requests.get(long_lived_url)
        long_lived_data = response.json()
        
        print(f"Long-lived token response: {long_lived_data}")
        
        if 'error' in long_lived_data:
            error_message = long_lived_data.get('error', {}).get('message', '不明なエラー')
            flash(f'長期アクセストークンの取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        long_lived_token = long_lived_data.get('access_token')
        
        # Webhookサブスクリプションを設定
        success, message = subscribe_to_webhook(page_id, long_lived_token)
        
        # ユーザー情報のデバッグ出力
        print(f"Current user ID: {current_user.id}")
        print(f"Current user username: {current_user.username}")
        print(f"Current user email: {current_user.email}")
        
        # ユーザーモデルに保存
        try:
            # 念のため、current_userがロードされているか確認
            if not current_user or not current_user.is_authenticated:
                print("WARNING: current_user not properly loaded!")
                # セッションからユーザーIDを取得して明示的にロード
                user_id = session.get('_user_id')
                print(f"Session user_id: {user_id}")
                if user_id:
                    user = User.query.get(int(user_id))
                    if user:
                        print(f"Loaded user from session: {user.id} - {user.username}")
                        # 明示的にロードしたユーザーに保存
                        user.facebook_token = long_lived_token
                        user.facebook_page_id = page_id
                        user.facebook_connected_at = datetime.utcnow()
                        db.session.commit()
                        print(f"Updated user {user.id} with Facebook data")
                    else:
                        print(f"Could not load user with ID {user_id}")
            else:
                # 通常のフロー
                current_user.facebook_token = long_lived_token
                current_user.facebook_page_id = page_id
                current_user.facebook_connected_at = datetime.utcnow()
                db.session.commit()
                print(f"Updated current_user {current_user.id} with Facebook data")
        except Exception as save_error:
            print(f"Error saving user data: {str(save_error)}")
            print(traceback.format_exc())
            flash('Facebook連携の設定中にエラーが発生しました。', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        if success:
            flash('DM自動返信機能を有効化しました', 'success')
        else:
            flash('DM自動返信機能を有効化しましたが、通知設定に問題がありました: {message}', 'warning')
        
    except Exception as e:
        print(f"DM自動返信機能の有効化中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        flash(f'DM自動返信機能の有効化中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('profile.autoreply_settings'))

def subscribe_to_webhook(page_id, page_access_token):
    """指定されたページのwebhookサブスクリプションを設定"""
    try:
        app_id = current_app.config.get('FACEBOOK_APP_ID')
        client_secret = current_app.config.get('FACEBOOK_APP_SECRET')
        webhook_url = request.host_url.rstrip('/') + '/webhook/instagram'
        
        # appsecret_proofを生成
        appsecret_proof = hmac.new(
            client_secret.encode('utf-8'),
            page_access_token.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # ページにサブスクリプションを設定
        url = f"https://graph.facebook.com/v22.0/{page_id}/subscribed_apps"
        params = {
            'access_token': page_access_token,
            'appsecret_proof': appsecret_proof,
            'subscribed_fields': 'messages,messaging_postbacks',
        }
        
        response = requests.post(url, params=params)
        data = response.json()
        
        print(f"Subscribe webhook response: {data}")
        
        if response.status_code == 200 and data.get('success'):
            return True, "Webhookサブスクリプションが成功しました"
        else:
            return False, f"Webhook登録エラー: {data.get('error', {}).get('message', '不明なエラー')}"
    
    except Exception as e:
        return False, f"Webhook設定中にエラー: {str(e)}"

@bp.route('/instagram/setup_webhook', methods=['POST'])
@login_required
def setup_instagram_webhook():
    """既存のInstagram連携アカウントに対してウェブフックを設定"""
    # CSRFトークンの検証（Flask-WTFの仕様変更に対応）
    try:
        # トークンの存在チェック
        csrf_token = request.form.get('csrf_token')
        if not csrf_token:
            flash('CSRFトークンがありません。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # CSRFトークン検証は必要に応じてフォームクラスで実施するか、
        # 標準的なルートでシンプルに保護する
    except Exception as e:
        flash(f'リクエスト検証エラー: {str(e)}', 'danger')
        return redirect(url_for('profile.sns_settings'))
    
    if not current_user.instagram_token or not current_user.instagram_username:
        flash('Instagram連携が完了していません', 'warning')
        return redirect(url_for('profile.sns_settings'))
    
    # 新しいFacebook認証フローにリダイレクト
    return redirect(url_for('profile.autoreply_settings'))

@bp.route('/disconnect/facebook', methods=['POST'])
@login_required
def disconnect_facebook():
    """DM自動返信機能を無効化（Facebook連携解除）"""
    # CSRFトークンの検証
    try:
        # トークンの存在チェック
        csrf_token = request.form.get('csrf_token')
        if not csrf_token:
            flash('CSRFトークンがありません。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # CSRFトークン検証は必要に応じてフォームクラスで実施するか、
        # 標準的なルートでシンプルに保護する
    except Exception as e:
        flash(f'リクエスト検証エラー: {str(e)}', 'danger')
        return redirect(url_for('profile.sns_settings'))
    
    # Meta側での連携解除処理
    facebook_page_id = current_user.facebook_page_id
    facebook_token = current_user.facebook_token
    webhook_subscription_id = current_user.webhook_subscription_id
    
    # API設定を取得
    app_id = current_app.config.get('INSTAGRAM_CLIENT_ID')
    app_secret = current_app.config.get('INSTAGRAM_CLIENT_SECRET')
    
    # 連携解除の結果を追跡
    api_success = True
    error_details = []
    
    try:
        # 1. ページのWebhookサブスクリプション解除
        if facebook_page_id and facebook_token:
            unsubscribe_success = unsubscribe_page_webhook(facebook_page_id, facebook_token)
            if unsubscribe_success:
                print(f"Page webhook successfully unsubscribed for page {facebook_page_id}")
            else:
                api_success = False
                error_details.append("ページWebhookの解除")
                print(f"Failed to unsubscribe page webhook for page {facebook_page_id}")
        
        # 2. Webhookサブスクリプション解除
        if webhook_subscription_id:
            unsubscribe_success = unsubscribe_instagram_webhook(current_user.instagram_business_id, current_user.instagram_token)
            if unsubscribe_success:
                print(f"Webhook subscription {webhook_subscription_id} successfully removed")
            else:
                api_success = False
                error_details.append("アプリWebhookの解除")
                print(f"Failed to remove webhook subscription {webhook_subscription_id}")
    except Exception as e:
        api_success = False
        error_details.append(f"APIエラー: {str(e)}")
        print(f"Error during Facebook disconnection: {str(e)}")
    
    # 連携情報をクリア
    try:
        current_user.facebook_token = None
        current_user.facebook_page_id = None
        current_user.webhook_subscription_id = None
        current_user.facebook_connected_at = None
        # 自動返信設定はそのまま保持する（再連携時に使えるように）
        db.session.commit()
        db_success = True
    except Exception as e:
        db_success = False
        error_details.append(f"データベースエラー: {str(e)}")
        print(f"Database error during Facebook disconnection: {str(e)}")
        db.session.rollback()
    
    # 結果に応じたフラッシュメッセージを表示
    if db_success:
        flash('DM自動返信機能を無効化しました', 'success')
    else:
        flash('DM自動返信機能の無効化中にエラーが発生しました。管理者にお問い合わせください。', 'danger')
    
    return redirect(url_for('profile.sns_settings'))

# データ削除エンドポイントはCSRF保護から除外
@csrf.exempt
@bp.route('/meta/data-deletion', methods=['POST'])
def meta_data_deletion_callback():
    """Metaプラットフォームからのデータ削除リクエストを処理するエンドポイント
    
    Meta Developers設定の「データ削除リクエスト」で設定するコールバックURL
    https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback
    """
    # リクエストの検証
    try:
        # 署名の検証
        signature = request.headers.get('x-hub-signature', '')
        if not signature:
            current_app.logger.error("Missing x-hub-signature in data deletion request")
            return jsonify({'success': False, 'message': 'Missing signature'}), 401
        
        # リクエストボディを取得
        if not request.data:
            current_app.logger.error("Empty request body in data deletion request")
            return jsonify({'success': False, 'message': 'Empty request body'}), 400
            
        request_body = request.data
        
        # アプリシークレットでHMAC-SHA256署名を計算
        app_secret = current_app.config.get('INSTAGRAM_CLIENT_SECRET')
        expected_signature = 'sha256=' + hmac.new(
            app_secret.encode('utf-8'),
            request_body,
            hashlib.sha256
        ).hexdigest()
        
        # 署名が一致しない場合は拒否
        if not hmac.compare_digest(signature, expected_signature):
            current_app.logger.error("Invalid signature in data deletion request")
            return jsonify({'success': False, 'message': 'Invalid signature'}), 401
        
        # JSONデータを解析
        data = request.get_json()
        
        # 必須フィールドの検証
        user_id = data.get('user_id')
        confirmation_code = data.get('confirmation_code')
        
        if not user_id or not confirmation_code:
            current_app.logger.error(f"Missing required fields in data deletion request: {data}")
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        # ユーザーデータを削除
        current_app.logger.info(f"Processing data deletion request for user_id: {user_id}, confirmation_code: {confirmation_code}")
        
        # Instagramユーザーを検索
        user = User.query.filter_by(instagram_user_id=user_id).first()
        
        if user:
            current_app.logger.info(f"Found user to delete data: {user.id}")
            
            # Meta関連データをクリア
            user.instagram_token = None
            user.instagram_user_id = None
            user.instagram_username = None
            user.instagram_connected_at = None
            user.facebook_token = None
            user.facebook_page_id = None
            user.webhook_subscription_id = None
            user.facebook_connected_at = None
            
            # 必要に応じて他のMeta関連データも削除
            # 実際のデータ削除範囲はプライバシーポリシーとデータ取り扱い方針に基づいて決定
            
            db.session.commit()
            current_app.logger.info(f"Successfully deleted Meta data for user: {user.id}")
        else:
            current_app.logger.info(f"No user found with Instagram user_id: {user_id}")
        
        # 必ずconfirmation_codeを返す（ユーザーが見つからなくても成功と返す必要がある）
        return jsonify({
            'confirmation_code': confirmation_code,
            'success': True
        })
        
    except Exception as e:
        current_app.logger.exception(f"Error processing data deletion request: {str(e)}")
        return jsonify({'success': False, 'message': 'Server error'}), 500

@bp.route('/enable_autoreply', methods=['POST'])
@login_required
def enable_autoreply():
    """自動返信機能を有効化する"""
    try:
        # CSRFトークンはFlask-WTFによって自動的に検証される
        
        # Instagramが連携されていない場合はエラー
        if not current_user.instagram_business_id or not current_user.instagram_token:
            flash('Instagram連携が必要です。', 'warning')
            return redirect(url_for('profile.sns_settings'))
        
        # 自動返信を有効化
        current_user.autoreply_enabled = True
        
        # 自動返信テンプレートが設定されていない場合はデフォルト値を設定
        if not current_user.autoreply_template:
            current_user.autoreply_template = "こんにちは！場所の詳細は {profile_url} で確認できます。"
            current_user.autoreply_last_updated = datetime.utcnow()
        
        db.session.commit()
        flash('自動返信機能を有効化しました。', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"自動返信機能の有効化中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        flash('自動返信機能の有効化中にエラーが発生しました。', 'danger')
    
    # 自動返信設定ページへリダイレクト
    return redirect(url_for('profile.autoreply_settings'))

@bp.route('/settings/url')
@login_required
def url_settings():
    """URL設定ページ"""
    return render_template('url_settings.html')

@bp.route('/settings/url', methods=['POST'])
@login_required
def update_url():
    """URLの更新処理"""
    display_name = request.form.get('display_name')
    password = request.form.get('password')
    
    # パスワード確認
    if not current_user.check_password(password):
        flash('パスワードが正しくありません。', 'danger')
        return redirect(url_for('profile.url_settings'))
    
    # 変更がない場合
    if current_user.display_name == display_name:
        flash('URLに変更はありません。', 'info')
        return redirect(url_for('profile.url_settings'))
    
    # 表示名の検証
    is_valid, message = User.validate_display_name(display_name)
    if not is_valid:
        flash(message, 'danger')
        return redirect(url_for('profile.url_settings'))
    
    # 表示名の更新
    current_user.display_name = display_name
    db.session.commit()
    
    flash('URLが更新されました。', 'success')
    return redirect(url_for('profile.url_settings'))

@bp.route('/<display_name>')
def display_name_profile(display_name):
    """表示名によるユーザープロファイル表示"""
    # 予約語チェック（システムで使用されるパスの場合はエラー）
    reserved_words = ['login', 'logout', 'signup', 'auth', 'admin', 'settings', 
                    'mypage', 'import', 'spot', 'api', 'static', 'upload', 
                    'profile', 'user', 'users', 'search', 'map', 'maps']
    if display_name.lower() in reserved_words:
        abort(404)
    
    user = User.query.filter_by(display_name=display_name).first_or_404()
    # アクティブなスポットのみを取得するように修正
    spots = Spot.query.filter_by(user_id=user.id, is_active=True).all()
    
    # スポットデータをJSONシリアライズ可能な形式に変換
    spots_data = []
    for spot in spots:
        # ユーザーがアップロードした写真
        user_photos = [p for p in spot.photos if not p.is_google_photo]
        user_photo_list = [{'photo_url': p.photo_url} for p in user_photos]

        # Google PhotosをPlace ID経由で取得
        google_photo_list = []
        if spot.google_place_id:
            google_photo_urls = get_google_photos_by_place_id(spot.google_place_id)
            google_photo_list = [{'photo_url': url} for url in google_photo_urls]
        
        # ユーザー写真とGoogle写真を結合
        all_photos = user_photo_list + google_photo_list

        spot_dict = {
            'id': spot.id,
            'name': spot.name,
            'location': spot.location or '',
            'summary_location': spot.summary_location or '',
            'latitude': spot.latitude,
            'longitude': spot.longitude,
            'category': spot.category or '',
            'description': spot.description or '',
            'rating': spot.rating,
            'photos': all_photos
        }
        spots_data.append(spot_dict)
    
    # Google Maps API Keyをconfigとして渡す
    from app.routes.public import GOOGLE_MAPS_API_KEY
    
    # ソーシャルアカウント情報を取得
    from app.models import SocialAccount
    social_accounts = SocialAccount.query.filter_by(user_id=user.id).first()
    
    return render_template('public/new_profile.html', 
                          user=user, 
                          spots=spots_data,
                          social_accounts=social_accounts,
                          config={'GOOGLE_MAPS_API_KEY': GOOGLE_MAPS_API_KEY})

@bp.route('/<display_name>/map')
def display_name_map(display_name):
    """表示名によるユーザーマップページ表示"""
    # 予約語チェック（システムで使用されるパスの場合はエラー）
    reserved_words = ['login', 'logout', 'signup', 'auth', 'admin', 'settings', 
                    'mypage', 'import', 'spot', 'api', 'static', 'upload', 
                    'profile', 'user', 'users', 'search', 'map', 'maps']
    if display_name.lower() in reserved_words:
        abort(404)
    
    user = User.query.filter_by(display_name=display_name).first_or_404()
    
    # アクティブなスポットを取得
    spots = Spot.query.filter_by(user_id=user.id, is_active=True).all()
    
    # スポットをJSONシリアライズ可能な形式に変換
    from app.models import SocialAccount
    spots_data = []
    for spot in spots:
        # ユーザーがアップロードした写真
        user_photos = [p for p in spot.photos if not p.is_google_photo]
        user_photo_list = [{'photo_url': p.photo_url} for p in user_photos]

        # Google PhotosをPlace ID経由で取得
        google_photo_list = []
        if spot.google_place_id:
            google_photo_urls = get_google_photos_by_place_id(spot.google_place_id)
            google_photo_list = [{'photo_url': url} for url in google_photo_urls]
        
        # ユーザー写真とGoogle写真を結合
        all_photos = user_photo_list + google_photo_list

        spot_dict = {
            'id': spot.id,
            'name': spot.name,
            'location': spot.location,
            'latitude': spot.latitude,
            'longitude': spot.longitude,
            'category': spot.category,
            'description': spot.description,
            'rating': spot.rating,
            'user_id': spot.user_id,
            'photos': all_photos
        }
        spots_data.append(spot_dict)
    
    # ソーシャルアカウント情報を取得
    social_accounts = SocialAccount.query.filter_by(user_id=user.id).all()
    
    # Google Maps API Keyをconfigとして渡す
    from app.routes.public import GOOGLE_MAPS_API_KEY
    
    return render_template('public/new_map.html',
                         user=user,
                         spots=spots_data,
                         social_accounts=social_accounts,
                         config={'GOOGLE_MAPS_API_KEY': GOOGLE_MAPS_API_KEY})

@bp.route('/settings/affiliate')
@login_required
def affiliate_settings():
    """アフィリエイト設定ページ"""
    return render_template('affiliate_settings.html')

@bp.route('/settings/affiliate', methods=['POST'])
@login_required
def update_affiliate_settings():
    """アフィリエイト設定の更新"""
    rakuten_affiliate_id = request.form.get('rakuten_affiliate_id', '').strip()
    
    # 更新して保存
    current_user.rakuten_affiliate_id = rakuten_affiliate_id
    db.session.commit()
    
    flash('アフィリエイト設定を保存しました', 'success')
    return redirect(url_for('profile.affiliate_settings'))

# ページのWebhookフィールドサブスクリプションを解除する
def unsubscribe_page_webhook(page_id, page_access_token):
    """
    ページのWebhookフィールドサブスクリプションを解除する
    
    Args:
        page_id (str): FacebookページID
        page_access_token (str): ページアクセストークン
    
    Returns:
        bool: 成功したかどうか
    """
    try:
        if not page_id or not page_access_token:
            return False
            
        # ページのサブスクリプションを削除
        webhook_url = f"https://graph.facebook.com/v22.0/{page_id}/subscribed_apps"
        params = {
            'access_token': page_access_token
        }
        
        # アクセストークンを隠してログ記録
        current_app.logger.info(f"Unsubscribing page webhook - Page ID: {page_id}, URL: {webhook_url}")
        
        response = requests.delete(webhook_url, params=params)
        
        # レスポンスをログに記録
        current_app.logger.info(f"Page webhook unsubscription response - Status: {response.status_code}, Body: {response.text}")
        
        # 成功レスポンスは {"success": true} が返ってくる
        if response.status_code == 200:
            result = response.json()
            return result.get('success', False)
        
        # エラーレスポンスの場合はログに記録
        current_app.logger.error(f"Page webhook unsubscription failed: {response.text}")
        return False
    
    except Exception as e:
        current_app.logger.exception(f"Error unsubscribing page webhook: {str(e)}")
        return False 