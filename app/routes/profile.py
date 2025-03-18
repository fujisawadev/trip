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
                page_info_url = f"https://graph.facebook.com/v22.0/me/accounts?access_token={long_lived_token}"
                page_response = requests.get(page_info_url)
                page_info = page_response.json()
                
                print(f"ページ情報レスポンス: {page_info}")
                
                if 'data' in page_info and len(page_info['data']) > 0:
                    # ページID（ビジネスアカウントID）を取得
                    page_id = page_info['data'][0]['id']
                    print(f"ビジネスアカウントID（ページID）: {page_id}")
                    
                    # ウェブフックサブスクリプションを設定
                    subscribe_url = f"https://graph.facebook.com/v22.0/{page_id}/subscribed_apps"
                    subscribe_data = {
                        'access_token': long_lived_token,
                        'subscribed_fields': 'messages'
                    }
                    
                    print(f"ウェブフックサブスクリプション設定を開始: URL={subscribe_url}")
                    subscribe_response = requests.post(subscribe_url, data=subscribe_data)
                    subscribe_result = subscribe_response.json()
                    
                    print(f"サブスクリプション結果: {subscribe_result}")
                    
                    if subscribe_response.status_code == 200 and subscribe_result.get('success'):
                        # ビジネスアカウントIDを保存
                        current_user.instagram_business_id = page_id
                        print(f"ページをウェブフックにサブスクライブしました: {page_id}")
                        flash('Instagram DMの自動返信機能の設定が完了しました', 'success')
                    else:
                        print(f"ページのサブスクライブに失敗: {subscribe_response.text}")
                        flash('Instagram DMの自動返信機能の設定に一部問題が発生しました', 'warning')
                else:
                    print("ページ情報の取得に失敗または該当するページが見つかりません")
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
    # CSRFトークンの検証
    if not request.form.get('csrf_token') or not current_app.csrf.validate_csrf(request.form.get('csrf_token')):
        flash('不正なリクエストです。', 'danger')
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

@bp.route('/instagram/setup_webhook', methods=['POST'])
@login_required
def setup_instagram_webhook():
    """既存のInstagram連携アカウントに対してウェブフックを設定"""
    # CSRFトークンの検証
    if not request.form.get('csrf_token') or not current_app.csrf.validate_csrf(request.form.get('csrf_token')):
        flash('不正なリクエストです。', 'danger')
        return redirect(url_for('profile.sns_settings'))
    
    if not current_user.instagram_token or not current_user.instagram_username:
        flash('Instagram連携が完了していません', 'warning')
        return redirect(url_for('profile.sns_settings'))
    
    try:
        # ページ情報を取得
        token = current_user.instagram_token
        print(f"既存アカウントのウェブフック設定を開始: ユーザー={current_user.username}, Instagram={current_user.instagram_username}")
        
        page_info_url = f"https://graph.facebook.com/v22.0/me/accounts?access_token={token}"
        page_response = requests.get(page_info_url)
        page_info = page_response.json()
        
        print(f"ページ情報レスポンス: {page_info}")
        
        if 'data' in page_info and len(page_info['data']) > 0:
            # ページIDを取得して保存
            page_id = page_info['data'][0]['id']
            print(f"ビジネスアカウントID（ページID）: {page_id}")
            
            # ウェブフックサブスクリプションを設定
            subscribe_url = f"https://graph.facebook.com/v22.0/{page_id}/subscribed_apps"
            subscribe_data = {
                'access_token': token,
                'subscribed_fields': 'messages'
            }
            
            print(f"ウェブフックサブスクリプション設定を開始: URL={subscribe_url}")
            subscribe_response = requests.post(subscribe_url, data=subscribe_data)
            subscribe_result = subscribe_response.json()
            
            print(f"サブスクリプション結果: {subscribe_result}")
            
            if subscribe_response.status_code == 200 and subscribe_result.get('success'):
                # ビジネスアカウントIDを保存
                current_user.instagram_business_id = page_id
                db.session.commit()
                flash('Instagram DMの自動返信機能の設定が完了しました', 'success')
            else:
                error_msg = subscribe_response.text if hasattr(subscribe_response, 'text') else '不明なエラー'
                flash(f'ウェブフック設定に失敗しました: {error_msg}', 'danger')
        else:
            flash('Instagramビジネスアカウント情報が取得できませんでした', 'danger')
    
    except Exception as e:
        import traceback
        print(f"ウェブフック設定中にエラー: {str(e)}")
        print(traceback.format_exc())
        flash(f'ウェブフック設定中にエラーが発生しました: {str(e)}', 'danger')
    
    return redirect(url_for('profile.sns_settings')) 