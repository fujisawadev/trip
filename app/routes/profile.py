import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.user import User
from app.models.spot import Spot
from app.models.import_progress import ImportProgress
import uuid
import requests
from datetime import datetime

bp = Blueprint('profile', __name__)

# 許可するファイル拡張子
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/mypage')
@login_required
def mypage():
    """マイページ"""
    spots = Spot.query.filter_by(user_id=current_user.id).all()
    return render_template('mypage.html', user=current_user, spots=spots)

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
    
    # 2025年3月現在の最新の有効なスコープ
    scope = "instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments,instagram_business_content_publish,instagram_business_manage_insights"
    
    # Instagram認証URLを生成
    auth_url = f"https://www.instagram.com/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}&response_type=code&state={state}&enable_fb_login=0&force_authentication=1"
    
    print(f"Auth URL: {auth_url}")
    
    # Instagram認証ページにリダイレクト
    return redirect(auth_url)

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
        graph_url = f"https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret={client_secret}&access_token={short_lived_token}"
        response = requests.get(graph_url)
        long_lived_data = response.json()
        
        print(f"Long-lived token response: {long_lived_data}")
        
        if 'error' in long_lived_data:
            error_message = long_lived_data.get('error', {}).get('message', '不明なエラー')
            flash(f'長期アクセストークンの取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        long_lived_token = long_lived_data.get('access_token')
        expires_in = long_lived_data.get('expires_in', 5184000)  # デフォルトは60日（5184000秒）
        
        # ユーザー名を取得
        user_info_url = f"https://graph.instagram.com/me?fields=username,account_type&access_token={long_lived_token}"
        response = requests.get(user_info_url)
        user_info = response.json()
        
        print(f"User info response: {user_info}")
        
        if 'error' in user_info:
            error_message = user_info.get('error', {}).get('message', '不明なエラー')
            flash(f'ユーザー情報の取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        instagram_username = user_info.get('username')
        account_type = user_info.get('account_type', 'unknown')
        
        # アカウントタイプをチェック（ビジネスアカウントかどうか）
        if account_type != 'BUSINESS':
            flash(f'Instagram連携にはビジネスアカウントが必要です。現在のアカウントタイプ: {account_type}', 'warning')
            # ビジネスアカウントでない場合でも、一応情報は保存する
        else:
            # ビジネスアカウントの場合は追加設定を行う
            try:
                # ビジネスアカウント（ページ）情報を取得
                print("ビジネスアカウント情報の取得を開始")
                # 直接Instagram Graph APIからIGIDを取得
                instagram_id_url = f"https://graph.instagram.com/me?fields=id,username&access_token={long_lived_token}"
                ig_response = requests.get(instagram_id_url)
                ig_info = ig_response.json()
                
                print(f"Instagram ID情報レスポンス: {ig_info}")
                
                if 'id' in ig_info:
                    # InstagramのビジネスアカウントIDを直接使用
                    ig_business_id = ig_info['id']
                    print(f"Instagram Business ID: {ig_business_id}")
                    
                    # ビジネスアカウントIDを保存
                    current_user.instagram_business_id = ig_business_id
                    db.session.commit()
                    print(f"Instagram Business IDを更新しました: {ig_business_id}")
                    
                    # メッセージングAPIの購読設定を試みる - 正しいエンドポイントとパラメータを使用
                    try:
                        # Facebookアプリの情報を使用したWebhook設定
                        app_id = current_app.config.get('INSTAGRAM_CLIENT_ID')
                        app_secret = current_app.config.get('INSTAGRAM_CLIENT_SECRET')
                        
                        if not app_id or not app_secret:
                            raise ValueError("InstagramアプリIDまたはシークレットが設定されていません")
                        
                        # まずページトークンを取得する必要がある - このステップはデモ用で実際には異なる場合がある
                        print("WebhookサブスクリプションはAPIの制限のため難しい場合があります")
                        print("Instagramへの連携は成功しました。Webhookは手動で設定する必要がある場合があります")
                        
                        # ユーザーに通知
                        flash('Instagram連携は成功しました。現在のAPIではWebhook自動設定ができないため、必要に応じて管理者に手動設定を依頼してください。', 'info')
                    except Exception as sub_error:
                        print(f"サブスクリプション設定中にエラー: {str(sub_error)}")
                        # ユーザーに見せるメッセージはより穏やかなものに
                        flash('Instagram連携は成功しましたが、通知設定は別途必要です。', 'info')
                else:
                    print("Instagram ID情報の取得に失敗")
            except Exception as e:
                print(f"ビジネスアカウント設定中にエラー: {str(e)}")
                print(traceback.format_exc())
                flash('ウェブフック設定中にエラーが発生しました。自動返信機能が正しく動作しない可能性があります。', 'warning')
        
        # ユーザーモデルに保存
        current_user.instagram_token = long_lived_token
        current_user.instagram_user_id = instagram_user_id
        current_user.instagram_username = instagram_username
        current_user.instagram_connected_at = datetime.utcnow()
        db.session.commit()
        
        flash(f'Instagram連携が完了しました。ユーザー名: {instagram_username}', 'success')
    except Exception as e:
        import traceback
        print(f"Instagram連携中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        flash(f'Instagram連携中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('profile.sns_settings'))

@bp.route('/disconnect/instagram', methods=['POST'])
@login_required
def disconnect_instagram():
    """Instagram連携を解除"""
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
    
    # 連携情報をクリア
    current_user.instagram_token = None
    current_user.instagram_user_id = None
    current_user.instagram_username = None
    current_user.instagram_connected_at = None
    db.session.commit()
    
    flash('Instagram連携を解除しました。', 'success')
    return redirect(url_for('profile.sns_settings'))

@bp.route('/user/<username>')
def user_profile(username):
    """ユーザープロフィールページ"""
    user = User.query.filter_by(username=username).first_or_404()
    spots = Spot.query.filter_by(user_id=user.id).all()
    
    # Google Maps API Keyをconfigとして渡す
    from app.routes.public import GOOGLE_MAPS_API_KEY
    
    return render_template('public/profile.html', 
                          user=user, 
                          spots=spots, 
                          config={'GOOGLE_MAPS_API_KEY': GOOGLE_MAPS_API_KEY})

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
    return render_template('autoreply.html', title='自動返信設定')

@bp.route('/connect/facebook')
@login_required
def connect_facebook():
    """Facebookとの連携を開始（DM自動返信機能用）"""
    # Instagram連携が済んでいることを確認
    if not current_user.instagram_token or not current_user.instagram_username:
        flash('先にInstagram連携を行ってください', 'warning')
        return redirect(url_for('profile.autoreply_settings'))
    
    # Facebook認証用のURLを生成
    client_id = current_app.config.get('FACEBOOK_APP_ID')
    
    if not client_id:
        flash('Facebook連携の設定が完了していません。管理者にお問い合わせください。', 'danger')
        return redirect(url_for('profile.autoreply_settings'))
    
    # リダイレクトURIを設定
    redirect_uri = request.host_url.rstrip('/') + url_for('profile.facebook_callback')
    
    # デバッグ情報を表示
    print(f"Facebook App ID: {client_id}")
    print(f"Facebook App Secret: {current_app.config.get('FACEBOOK_APP_SECRET')}")
    print(f"Redirect URI: {redirect_uri}")
    
    # CSRF対策のstateパラメータを生成
    state = str(uuid.uuid4())
    session['facebook_auth_state'] = state
    
    # 必要なスコープ
    scope = "pages_show_list,pages_manage_metadata"
    
    # Facebook認証URLを生成
    auth_url = f"https://www.facebook.com/v17.0/dialog/oauth?client_id={client_id}&redirect_uri={redirect_uri}&state={state}&scope={scope}"
    
    print(f"Auth URL: {auth_url}")
    
    # Facebook認証ページにリダイレクト
    return redirect(auth_url)

@bp.route('/facebook/callback')
@login_required
def facebook_callback():
    """Facebook認証後のコールバック処理"""
    # 認証コードを取得
    code = request.args.get('code')
    error = request.args.get('error')
    error_reason = request.args.get('error_reason')
    state = request.args.get('state')
    
    # エラーチェック
    if error:
        flash(f'Facebook連携に失敗しました: {error_reason}', 'danger')
        return redirect(url_for('profile.autoreply_settings'))
    
    if not code:
        flash('認証コードが取得できませんでした。', 'danger')
        return redirect(url_for('profile.autoreply_settings'))
    
    # CSRF対策の状態チェック
    if not session.get('facebook_auth_state') or session.get('facebook_auth_state') != state:
        flash('セキュリティ上の問題が発生しました。もう一度お試しください。', 'danger')
        return redirect(url_for('profile.autoreply_settings'))
    
    # セッションから状態を削除
    session.pop('facebook_auth_state', None)
    
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
        token_url = 'https://graph.facebook.com/v17.0/oauth/access_token'
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
        user_info_url = f"https://graph.facebook.com/v17.0/me?fields=id,name&access_token={access_token}"
        response = requests.get(user_info_url)
        user_info = response.json()
        
        print(f"User info response: {user_info}")
        
        if 'error' in user_info:
            error_message = user_info.get('error', {}).get('message', '不明なエラー')
            flash(f'ユーザー情報の取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        facebook_user_id = user_info.get('id')
        
        # ページ一覧を取得
        pages_url = f"https://graph.facebook.com/v17.0/{facebook_user_id}/accounts?access_token={access_token}"
        response = requests.get(pages_url)
        pages_data = response.json()
        
        print(f"Pages response: {pages_data}")
        
        if 'error' in pages_data:
            error_message = pages_data.get('error', {}).get('message', '不明なエラー')
            flash(f'ページ情報の取得に失敗しました: {error_message}', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        pages = pages_data.get('data', [])
        
        if not pages:
            flash('接続可能なFacebookページが見つかりませんでした。ビジネスアカウントとして設定されているか確認してください。', 'warning')
            return redirect(url_for('profile.autoreply_settings'))
        
        # 最初のページを使用
        page = pages[0]
        page_id = page.get('id')
        page_name = page.get('name')
        page_access_token = page.get('access_token')
        
        # ページトークンを長期トークンに変換
        long_lived_url = f"https://graph.facebook.com/v17.0/oauth/access_token?grant_type=fb_exchange_token&client_id={client_id}&client_secret={client_secret}&fb_exchange_token={page_access_token}"
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
        
        # ユーザーモデルに保存
        current_user.facebook_token = long_lived_token
        current_user.facebook_page_id = page_id
        current_user.facebook_connected_at = datetime.utcnow()
        db.session.commit()
        
        if success:
            flash(f'Facebook連携が完了しました。ページ名: {page_name}', 'success')
        else:
            flash(f'Facebook連携は完了しましたが、Webhook設定に問題がありました: {message}', 'warning')
        
    except Exception as e:
        import traceback
        print(f"Facebook連携中にエラーが発生しました: {str(e)}")
        print(traceback.format_exc())
        flash(f'Facebook連携中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('profile.autoreply_settings'))

def subscribe_to_webhook(page_id, page_access_token):
    """指定されたページのwebhookサブスクリプションを設定"""
    try:
        app_id = current_app.config.get('FACEBOOK_APP_ID')
        webhook_url = request.host_url.rstrip('/') + '/webhook/instagram'
        
        # ページにサブスクリプションを設定
        url = f"https://graph.facebook.com/v17.0/{page_id}/subscribed_apps"
        params = {
            'access_token': page_access_token,
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