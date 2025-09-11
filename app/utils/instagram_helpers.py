from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
import requests

from flask import current_app
from app import db


def extract_cursor_from_url(url):
    """URLからafterパラメータを抽出する"""
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if 'after' in query_params:
            return query_params['after'][0]
        return None
    except Exception:
        return None


def refresh_user_instagram_token_if_needed(user, threshold_days: int = 14) -> bool:
    """ユーザーの長期アクセストークンを必要に応じてリフレッシュする。

    戻り値: 更新した場合 True、不要/失敗時 False
    """
    try:
        if not getattr(user, 'instagram_token', None):
            return False

        now = datetime.utcnow()
        expires_at = getattr(user, 'instagram_token_expires_at', None)

        # 有効期限が未保存なら、リフレッシュで明確化
        need_refresh = False
        if expires_at is None:
            need_refresh = True
        else:
            remaining = expires_at - now
            if remaining <= timedelta(days=threshold_days):
                need_refresh = True

        if not need_refresh:
            return False

        access_token = user.instagram_token
        api_ver = current_app.config.get('INSTAGRAM_API_VERSION', 'v22.0')
        url = f"https://graph.instagram.com/{api_ver}/refresh_access_token"
        params = {
            'grant_type': 'ig_refresh_token',
            'access_token': access_token,
        }

        resp = requests.get(url, params=params)
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code == 200 and data.get('access_token'):
            new_token = data['access_token']
            expires_in = int(data.get('expires_in', 60 * 24 * 60 * 60))  # デフォルト60日
            user.instagram_token = new_token
            user.instagram_token_expires_at = now + timedelta(seconds=expires_in)
            user.instagram_token_last_refreshed_at = now
            db.session.commit()
            current_app.logger.info(f"Refreshed IG token for user {user.id}; expires_at={user.instagram_token_expires_at}")
            return True

        # 失敗（無効トークンなど）は呼び出し側でハンドリング
        current_app.logger.info(f"IG token refresh skipped/failed for user {user.id}: status={resp.status_code}, data={data}")
        return False

    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        current_app.logger.warning(f"IG token refresh error for user {getattr(user, 'id', 'unknown')}: {e}")
        return False


def validate_instagram_token(user, timeout_sec: float = 5.0):
    """アクセストークンの健全性チェック。

    戻り値: (is_valid: bool, reason: str)
      reason: 'ok' | 'expired' | 'invalid' | 'no_token' | 'temporary_error'
    """
    try:
        if not getattr(user, 'instagram_token', None):
            return False, 'no_token'

        now = datetime.utcnow()
        expires_at = getattr(user, 'instagram_token_expires_at', None)
        if expires_at and now > expires_at:
            return False, 'expired'

        api_ver = current_app.config.get('INSTAGRAM_API_VERSION', 'v22.0')
        url = f"https://graph.instagram.com/{api_ver}/me"
        resp = requests.get(url, params={'fields': 'id', 'access_token': user.instagram_token}, timeout=timeout_sec)
        if resp.status_code == 200 and resp.json().get('id'):
            return True, 'ok'

        # 非200の場合は内容を判定
        try:
            ed = resp.json().get('error', {})
        except Exception:
            ed = {}
        msg = str(ed.get('message', '')).lower()
        code = ed.get('code')
        if code == 190 or 'invalid' in msg or 'invalidated' in msg:
            return False, 'invalid'
        if 'expired' in msg:
            return False, 'expired'
        return False, 'temporary_error'
    except Exception:
        return False, 'temporary_error'