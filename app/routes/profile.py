import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db, csrf
from app.models.user import User
from app.models.spot import Spot
from app.models.import_progress import ImportProgress
import uuid
import requests
from datetime import datetime
import hashlib
import hmac
import json
import random
import string
from urllib.parse import quote_plus

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
    instagram_connected = current_user.instagram_token is not None
    
    return render_template('sns.html', instagram_connected=instagram_connected)

@bp.route('/connect/instagram')
@login_required
def connect_instagram():
    """Instagramビジネスログイン認証フローを開始する
    新しいInstagram API with Instagram Loginを使用して
    Facebookページなしで直接Instagramに接続します
    """
    try:
        # メタアプリのIDとシークレットを取得
        client_id = current_app.config.get('META_APP_ID')
        client_secret = current_app.config.get('META_APP_SECRET')
        
        # リダイレクトURIを設定
        instagram_callback_url = url_for('profile.instagram_callback', _external=True)
        print(f"Instagram認証コールバックURL: {instagram_callback_url}")
        
        # クライアントIDが設定されているか確認
        if not client_id:
            flash('メタアプリのIDが設定されていません。', 'danger')
            print("メタアプリのIDが設定されていません。")
            return redirect(url_for('profile.sns_settings'))
        
        # スコープを設定 - 新しいInstagram API with Instagram Loginのために更新
        scope = [
            'instagram_basic',
            'instagram_manage_messages',
            'instagram_manage_comments',
            'public_profile',
            'instagram_manage_insights',
            'instagram_content_publish'
        ]
        
        # Instagramのログインに直接移動するクエリパラメータを追加
        state = {
            'csrf_token': generate_csrf_token(),
            'force_instagram_login': True  # これを追加することでInstagramログインを強制
        }
        
        # 認証URLを構築
        auth_url = f"https://www.instagram.com/oauth/authorize?client_id={client_id}&redirect_uri={quote_plus(instagram_callback_url)}&scope={','.join(scope)}&response_type=code&state={json.dumps(state)}"
        
        print(f"Instagram認証URL: {auth_url}")
        
        # ユーザーに認証URLにリダイレクト
        return redirect(auth_url)
    except Exception as e:
        print(f"Instagram認証フロー開始中にエラーが発生しました: {str(e)}")
        flash('Instagram認証フローの開始中にエラーが発生しました。', 'danger')
        return redirect(url_for('profile.sns_settings'))

@bp.route('/instagram-callback')
def instagram_callback():
    """Instagramビジネスログイン認証フローのコールバック処理
    新しいInstagram API with Instagram Loginを使用して
    Facebookページなしで直接Instagramに接続します
    """
    try:
        # 認証コードとエラーパラメータをチェック
        code = request.args.get('code')
        error = request.args.get('error')
        error_reason = request.args.get('error_reason')
        error_description = request.args.get('error_description')
        
        # エラーが発生した場合
        if error:
            error_message = f"Instagram認証エラー: {error}, 理由: {error_reason}, 説明: {error_description}"
            print(error_message)
            flash(f'Instagram連携中にエラーが発生しました: {error_description}', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # 認証コードがない場合
        if not code:
            print("Instagram認証コードがリクエストに含まれていません。")
            flash('Instagram認証情報が不足しています。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # メタアプリのIDとシークレットを取得
        client_id = current_app.config.get('META_APP_ID')
        client_secret = current_app.config.get('META_APP_SECRET')
        
        # コールバックURLを設定
        instagram_callback_url = url_for('profile.instagram_callback', _external=True)
        
        # トークン取得のためのパラメータを設定
        token_params = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': instagram_callback_url
        }
        
        # トークンAPIエンドポイント
        token_url = 'https://api.instagram.com/oauth/access_token'
        
        # アクセストークンを取得
        print(f"Instagramトークン取得リクエスト: URL={token_url}, params={token_params}")
        token_response = requests.post(token_url, data=token_params)
        
        # レスポンスの確認
        if token_response.status_code != 200:
            error_message = f"Instagramトークン取得エラー: ステータスコード {token_response.status_code}, レスポンス {token_response.text}"
            print(error_message)
            flash('Instagramトークンの取得に失敗しました。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # トークンレスポンスをJSONとしてパース
        token_data = token_response.json()
        short_lived_token = token_data.get('access_token')
        user_id = token_data.get('user_id')
        
        if not short_lived_token or not user_id:
            print(f"InstagramトークンまたはユーザーIDがレスポンスに含まれていません: {token_data}")
            flash('InstagramトークンまたはユーザーIDの取得に失敗しました。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # ショートリブドトークンを長期トークンに変換
        long_lived_params = {
            'client_secret': client_secret,
            'access_token': short_lived_token,
            'grant_type': 'ig_exchange_token'
        }
        
        # 長期トークン取得APIエンドポイント
        long_lived_url = 'https://graph.instagram.com/access_token'
        
        print(f"Instagram長期トークン取得リクエスト: URL={long_lived_url}")
        long_lived_response = requests.get(long_lived_url, params=long_lived_params)
        
        # レスポンスの確認
        if long_lived_response.status_code != 200:
            error_message = f"Instagram長期トークン取得エラー: ステータスコード {long_lived_response.status_code}, レスポンス {long_lived_response.text}"
            print(error_message)
            flash('Instagram長期トークンの取得に失敗しました。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # 長期トークンをJSONとしてパース
        long_lived_data = long_lived_response.json()
        long_lived_token = long_lived_data.get('access_token')
        
        if not long_lived_token:
            print(f"Instagram長期トークンがレスポンスに含まれていません: {long_lived_data}")
            flash('Instagram長期トークンの取得に失敗しました。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # Instagramビジネスアカウント情報を取得
        print(f"Instagramプロフィール情報取得: user_id={user_id}")
        graph_url = f'https://graph.instagram.com/v18.0/{user_id}'
        graph_params = {
            'fields': 'id,username,account_type,media_count',
            'access_token': long_lived_token
        }
        
        profile_response = requests.get(graph_url, params=graph_params)
        
        # レスポンスの確認
        if profile_response.status_code != 200:
            error_message = f"Instagramプロフィール取得エラー: ステータスコード {profile_response.status_code}, レスポンス {profile_response.text}"
            print(error_message)
            flash('Instagramプロフィール情報の取得に失敗しました。', 'danger')
            return redirect(url_for('profile.sns_settings'))
        
        # プロフィール情報をJSONとしてパース
        profile_data = profile_response.json()
        instagram_business_id = profile_data.get('id')
        instagram_username = profile_data.get('username')
        account_type = profile_data.get('account_type')
        
        print(f"Instagramプロフィール情報: id={instagram_business_id}, username={instagram_username}, account_type={account_type}")
        
        # プロフェッショナルアカウントかをチェック
        if account_type not in ['BUSINESS', 'CREATOR']:
            print(f"Instagramアカウント種別がビジネスまたはクリエイターではありません: {account_type}")
            flash('Instagramビジネスまたはクリエイターアカウントが必要です。', 'warning')
            # 一応続行するが警告を表示
        
        # ユーザーモデルを更新
        current_user.instagram_token = long_lived_token
        current_user.instagram_business_id = instagram_business_id
        current_user.instagram_username = instagram_username
        db.session.commit()
        
        # Webhookを設定
        print("Instagramウェブフックの登録を開始します")
        result = setup_instagram_direct_webhook(
            client_id, 
            client_secret,
            url_for('api_webhook_blueprint.instagram', _external=True)
        )
        
        if result:
            # ウェブフック登録成功時、ユーザーのアカウントをウェブフックに購読登録
            subscribe_result = subscribe_instagram_user_webhook(
                instagram_business_id, 
                long_lived_token
            )
            
            if subscribe_result:
                print(f"Instagramウェブフック登録完了: user_id={current_user.id}, instagram_business_id={instagram_business_id}")
                flash('Instagramビジネスアカウントの連携に成功しました。', 'success')
            else:
                print(f"Instagramウェブフック購読登録に失敗: user_id={current_user.id}, instagram_business_id={instagram_business_id}")
                flash('Instagramウェブフックの購読登録に失敗しましたが、アカウント連携は完了しました。', 'warning')
        else:
            print(f"Instagramウェブフックの登録に失敗: user_id={current_user.id}, instagram_business_id={instagram_business_id}")
            flash('Instagramウェブフックの登録に失敗しましたが、アカウント連携は完了しました。', 'warning')
        
        # 成功メッセージを表示して設定ページにリダイレクト
        return redirect(url_for('profile.sns_settings'))
    except Exception as e:
        print(f"Instagram認証コールバック処理中にエラーが発生しました: {str(e)}")
        traceback.print_exc()
        flash('Instagram連携処理中にエラーが発生しました。', 'danger')
        return redirect(url_for('profile.sns_settings'))

def setup_instagram_direct_webhook(app_id, app_secret, webhook_url):
    """Instagramウェブフックを直接設定する（Facebookページなし）"""
    try:
        # アプリアクセストークンを取得
        token_url = 'https://graph.facebook.com/oauth/access_token'
        token_params = {
            'client_id': app_id,
            'client_secret': app_secret,
            'grant_type': 'client_credentials'
        }
        
        # センシティブ情報を含むログから秘密情報を隠す
        log_params = token_params.copy()
        log_params['client_secret'] = '********'
        print(f"アプリアクセストークン取得リクエスト: URL={token_url}, params={log_params}")
        
        token_response = requests.get(token_url, params=token_params)
        
        # レスポンスの確認
        if token_response.status_code != 200:
            print(f"アプリアクセストークン取得エラー: ステータスコード {token_response.status_code}, レスポンス {token_response.text}")
            return False
        
        # トークンをJSONとしてパース
        token_data = token_response.json()
        app_access_token = token_data.get('access_token')
        
        if not app_access_token:
            print(f"アプリアクセストークンがレスポンスに含まれていません: {token_data}")
            return False
        
        # ウェブフックを設定
        webhook_url = f'https://graph.facebook.com/v18.0/{app_id}/subscriptions'
        
        # コールバック検証用のトークンを生成（ランダムな文字列）
        verify_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        
        # ウェブフック設定パラメータ
        webhook_params = {
            'object': 'instagram',  # 'instagram'を対象にする
            'callback_url': webhook_url,
            'verify_token': verify_token,
            'fields': 'messages,comments',  # 監視するフィールド
            'access_token': app_access_token
        }
        
        # センシティブ情報を含むログから秘密情報を隠す
        log_params = webhook_params.copy()
        log_params['access_token'] = '********'
        log_params['verify_token'] = '********'
        print(f"ウェブフック設定リクエスト: URL={webhook_url}, params={log_params}")
        
        webhook_response = requests.post(webhook_url, params=webhook_params)
        
        # レスポンスの確認
        if webhook_response.status_code != 200:
            print(f"ウェブフック設定エラー: ステータスコード {webhook_response.status_code}, レスポンス {webhook_response.text}")
            return False
        
        # 設定の確認
        response_data = webhook_response.json()
        success = response_data.get('success', False)
        
        if not success:
            print(f"ウェブフック設定が成功しませんでした: {response_data}")
            return False
        
        print(f"ウェブフック設定成功: {response_data}")
        
        # 検証トークンを設定に保存
        current_app.config['INSTAGRAM_WEBHOOK_VERIFY_TOKEN'] = verify_token
        
        return True
    except Exception as e:
        print(f"ウェブフック設定中にエラーが発生しました: {str(e)}")
        traceback.print_exc()
        return False

def subscribe_instagram_user_webhook(instagram_business_id, instagram_token):
    """ユーザーのInstagramアカウントをウェブフックに購読登録する"""
    try:
        # ユーザーのウェブフック購読を設定
        subscribe_url = f'https://graph.instagram.com/v18.0/{instagram_business_id}/subscribed_apps'
        
        # 購読パラメータ
        subscribe_params = {
            'access_token': instagram_token
        }
        
        print(f"ウェブフック購読リクエスト: URL={subscribe_url}, instagram_business_id={instagram_business_id}")
        
        subscribe_response = requests.post(subscribe_url, params=subscribe_params)
        
        # レスポンスの確認
        if subscribe_response.status_code != 200:
            print(f"ウェブフック購読エラー: ステータスコード {subscribe_response.status_code}, レスポンス {subscribe_response.text}")
            return False
        
        # 購読の確認
        response_data = subscribe_response.json()
        success = response_data.get('success', False)
        
        if not success:
            print(f"ウェブフック購読が成功しませんでした: {response_data}")
            return False
        
        print(f"ウェブフック購読成功: {response_data}")
        return True
    except Exception as e:
        print(f"ウェブフック購読中にエラーが発生しました: {str(e)}")
        traceback.print_exc()
        return False

@bp.route('/disconnect-instagram', methods=['POST'])
@login_required
def disconnect_instagram():
    """Instagramアカウント連携を解除する"""
    try:
        if current_user.instagram_token:
            print(f"Instagramアカウント連携を解除します: user_id={current_user.id}, instagram_username={current_user.instagram_username}")
            
            # アクセストークンを無効化（セキュリティのため）
            try:
                revoke_url = 'https://graph.instagram.com/access_token/revoke'
                revoke_params = {
                    'access_token': current_user.instagram_token
                }
                
                print("Instagramトークン無効化リクエスト送信")
                revoke_response = requests.get(revoke_url, params=revoke_params)
                
                if revoke_response.status_code == 200:
                    print("Instagramトークン無効化成功")
                else:
                    print(f"Instagramトークン無効化エラー: ステータスコード {revoke_response.status_code}, レスポンス {revoke_response.text}")
            except Exception as e:
                print(f"Instagramトークン無効化中にエラーが発生しました: {str(e)}")
                # 続行して他の情報をクリアする
                pass
            
            # ユーザー情報から連携情報をクリア
            current_user.instagram_token = None
            current_user.instagram_business_id = None
            current_user.instagram_username = None
            
            # Facebookページ連携情報も互換性のためにクリア（新API移行後の場合）
            current_user.facebook_token = None
            current_user.facebook_page_id = None
            
            db.session.commit()
            
            flash('Instagramアカウントの連携を解除しました。', 'success')
        else:
            flash('Instagramアカウントは連携されていません。', 'warning')
        
        return redirect(url_for('profile.sns_settings'))
    except Exception as e:
        print(f"Instagram連携解除中にエラーが発生しました: {str(e)}")
        flash('Instagram連携解除中にエラーが発生しました。', 'danger')
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
            flash('接続可能なFacebookページが見つかりませんでした。ビジネスアカウントと接続されているか確認してください。', 'warning')
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
            flash('接続可能なFacebookページが見つかりませんでした。ビジネスアカウントとして設定されているか確認してください。', 'warning')
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
            import traceback
            print(traceback.format_exc())
            flash('Facebook連携の設定中にエラーが発生しました。', 'danger')
            return redirect(url_for('profile.autoreply_settings'))
        
        if success:
            flash('DM自動返信機能を有効化しました', 'success')
        else:
            flash('DM自動返信機能を有効化しましたが、通知設定に問題がありました: {message}', 'warning')
        
    except Exception as e:
        import traceback
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
            unsubscribe_success = unsubscribe_webhook(app_id, app_secret, webhook_subscription_id)
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