import os
from typing import Any, Dict, List, Optional
import requests
from flask import current_app


def _cfg(key: str, default: Optional[str] = None) -> Optional[str]:
    return current_app.config.get(key) if current_app else os.environ.get(key, default)


def _auth() -> Optional[requests.auth.AuthBase]:
    login = _cfg('DATAFORSEO_LOGIN')
    password = _cfg('DATAFORSEO_PASSWORD')
    if not login or not password:
        return None
    return requests.auth.HTTPBasicAuth(login, password)


def _base_url() -> str:
    return _cfg('DATAFORSEO_BASE_URL', 'https://api.dataforseo.com').rstrip('/')


def search_hotels(
    keyword: str,
    location_name: str = 'Japan',
    language_code: str = 'ja',
    check_in: Optional[str] = None,
    check_out: Optional[str] = None,
    currency: str = 'JPY',
    adults: int = 2,
    timeout_sec: float = 10.0,
) -> List[Dict[str, Any]]:
    """DataForSEO: Google hotel_searches live

    Returns list of items. Each item may contain 'hotel_identifier', 'title', 'prices', etc.
    """
    auth = _auth()
    if auth is None:
        return []

    url = f"{_base_url()}/v3/business_data/google/hotel_searches/live"
    payload = [
        {
            "language_code": language_code or _cfg('DATAFORSEO_DEFAULT_LANGUAGE', 'ja'),
            "location_name": location_name or _cfg('DATAFORSEO_DEFAULT_LOCATION', 'Japan'),
            "keyword": keyword,
            **({"check_in": check_in} if check_in else {}),
            **({"check_out": check_out} if check_out else {}),
            "currency": currency,
            "adults": int(adults) if adults is not None else 2,
        }
    ]
    try:
        resp = requests.post(url, json=payload, auth=auth, timeout=timeout_sec)
        if resp.status_code != 200:
            return []
        data = resp.json()
        tasks = data.get('tasks') or []
        if not tasks:
            return []
        first_task = tasks[0]
        results = first_task.get('result') or []
        if not results:
            return []
        first_result = results[0]
        items = first_result.get('items') or []
        return items
    except Exception:
        return []


def fetch_hotel_offers(
    hotel_identifier: str,
    language_code: str = 'ja',
    location_name: str = 'Japan',
    check_in: Optional[str] = None,
    check_out: Optional[str] = None,
    currency: str = 'JPY',
    adults: int = 2,
    timeout_sec: float = 12.0,
) -> Dict[str, Any]:
    """DataForSEO: Google hotel_info live advanced

    Returns a dict with optional keys: title, prices(list), currency, etc.
    """
    auth = _auth()
    if auth is None:
        return {}

    url = f"{_base_url()}/v3/business_data/google/hotel_info/live/advanced"
    payload = [
        {
            "language_code": language_code or _cfg('DATAFORSEO_DEFAULT_LANGUAGE', 'ja'),
            "location_name": location_name or _cfg('DATAFORSEO_DEFAULT_LOCATION', 'Japan'),
            "hotel_identifier": hotel_identifier,
            **({"check_in": check_in} if check_in else {}),
            **({"check_out": check_out} if check_out else {}),
            "currency": currency,
            "adults": int(adults) if adults is not None else 2,
        }
    ]
    try:
        resp = requests.post(url, json=payload, auth=auth, timeout=timeout_sec)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        tasks = data.get('tasks') or []
        if not tasks:
            return {}
        first_task = tasks[0]
        results = first_task.get('result') or []
        if not results:
            return {}
        first_result = results[0]
        return first_result
    except Exception:
        return {}


def normalize_offers_from_hotel_info(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert DataForSEO hotel_info result to offers list in our schema.

    直リンク優先のフィルタを適用:
    - 直リンク定義: url があり、domain が google.* ではない
    - 直リンク内は is_paid == False を優先（先頭に）し、次に価格昇順
    - 直リンクが1件も無い場合のみ、google.*（リダイレクト）の最安1件にフォールバック

    Output item keys: provider, price, currency, deeplink, is_min_price(False)
    """
    if not result:
        return []
    prices_obj = result.get('prices') or {}
    items = prices_obj.get('items') or []
    if not isinstance(items, list) or not items:
        return []

    def is_google_domain(domain: Optional[str]) -> bool:
        if not domain:
            return False
        # シンプル実装: 'google.' を含むものをGoogleドメインとみなす（例: google.co.jp, www.google.com）
        return 'google.' in domain

    def is_whitelisted_provider(it: Dict[str, Any]) -> bool:
        title = (it.get('title') or '').strip()
        domain = (it.get('domain') or '').strip().lower()
        url = (it.get('url') or '').strip().lower()

        # 許可ドメイン（部分一致）
        allowed_domains = [
            'travel.yahoo.co.jp',  # Yahoo!トラベル
            'ikyu.com',            # 一休.com
            'booking.com',         # Booking.com
            'agoda.com',           # Agoda
            'expedia.co.jp',       # Expedia.co.jp
            'jalan.net',           # じゃらん
            'rurubu.travel',       # るるぶトラベル
            'trivago.jp',          # trivago.jp
        ]

        # 許可タイトル（部分一致/大小無視は英字のみ）
        allowed_titles = [
            'Yahoo!トラベル',
            '一休',
            'Booking.com',
            'Agoda',
            'Expedia',
            'じゃらん',
            'るるぶトラベル',
            'trivago',
        ]

        # ドメインで判定
        for d in allowed_domains:
            if domain.find(d) != -1 or url.find(d) != -1:
                return True

        # タイトルで判定（日本語はそのまま、英字は小文字比較）
        lt = title.lower()
        for t in allowed_titles:
            if t.isascii():
                if lt.find(t.lower()) != -1:
                    return True
            else:
                if title.find(t) != -1:
                    return True
        return False

    def is_blocked_provider(it: Dict[str, Any]) -> bool:
        title = ((it.get('title') or '').strip()).lower()
        domain = ((it.get('domain') or '').strip()).lower()
        url = ((it.get('url') or '').strip()).lower()
        # 明示的に除外したいプロバイダ
        blocked_keywords = [
            'wego',            # Wego Marketplace など
        ]
        for k in blocked_keywords:
            if k in title or k in domain or k in url:
                return True
        return False

    # 直リンク候補: urlあり & googleドメイン以外
    direct_items: List[Dict[str, Any]] = [
        it for it in items
        if isinstance(it, dict) and it.get('url') and not is_google_domain(it.get('domain')) and not is_blocked_provider(it)
    ]
    # 日本向けOTAのホワイトリストを適用
    direct_items = [it for it in direct_items if is_whitelisted_provider(it)]

    def price_value(v: Any) -> Optional[float]:
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    # 直リンクがあれば、is_paid=False 優先で価格昇順
    if direct_items:
        direct_items_sorted = sorted(
            direct_items,
            key=lambda it: (
                it.get('is_paid', False) is True,  # Falseが先
                price_value(it.get('price')) if price_value(it.get('price')) is not None else float('inf')
            )
        )
        offers: List[Dict[str, Any]] = []
        for it in direct_items_sorted:
            offers.append({
                'provider': it.get('title') or '提携サイト',
                'price': it.get('price'),
                'currency': it.get('currency'),
                'deeplink': it.get('url'),
                'is_min_price': False,
            })
        return offers

    # 直リンクが無い場合: google.* リダイレクトの中からホワイトリストの最安のみ採用
    google_items: List[Dict[str, Any]] = [
        it for it in items
        if isinstance(it, dict) and it.get('url') and is_google_domain(it.get('domain')) and not is_blocked_provider(it) and is_whitelisted_provider(it)
    ]
    if not google_items:
        # 最後のフォールバック: itemsが無い/対象外の場合でも、全体価格とcheck_urlがあれば1件を生成
        overall_price = None
        try:
            overall_price = (result.get('prices') or {}).get('price')
        except Exception:
            overall_price = None
        check_url = result.get('check_url')
        if check_url:
            return [{
                'provider': 'Google Hotels',
                'price': overall_price,
                'currency': (result.get('prices') or {}).get('currency', 'JPY'),
                'deeplink': check_url,
                'is_min_price': False,
            }]
        return []
    google_items_sorted = sorted(
        google_items,
        key=lambda it: price_value(it.get('price')) if price_value(it.get('price')) is not None else float('inf')
    )
    best = google_items_sorted[0]
    return [{
        'provider': best.get('title') or '提携サイト',
        'price': best.get('price'),
        'currency': best.get('currency'),
        'deeplink': best.get('url'),
        'is_min_price': False,
    }]


