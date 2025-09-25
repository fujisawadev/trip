import os
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl, quote


def _cfg(key: str, default: Optional[str] = None) -> Optional[str]:
    # Prefer Flask config via env when available; fallback to os.environ
    return os.environ.get(key, default)


def _append_params(url: str, params: Dict[str, Optional[str]]) -> str:
    try:
        parsed = urlparse(url)
        query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for k, v in params.items():
            if v is None or v == "":
                continue
            query_pairs[k] = str(v)
        new_query = urlencode(query_pairs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return url


def build_stay22_allez_for_booking(lat: Optional[float], lng: Optional[float], hotel_name: Optional[str], address: Optional[str], check_in: Optional[str], check_out: Optional[str]) -> Optional[str]:
    """Stay22 Allez 方式のリンクを生成（Booking向け）。
    優先度: lat/lng > (hotelname + address)。
    日付は任意（指定あれば付与）。
    """
    aid = _cfg('STAY22_AID')
    if not aid:
        return None
    # Booking専用エンドポイントに固定
    base = 'https://www.stay22.com/allez/booking'
    params: Dict[str, Optional[str]] = {
        'aid': aid,
    }
    try:
        if lat is not None and lng is not None:
            params['lat'] = str(lat)
            params['lng'] = str(lng)
        else:
            # lat/lngが無い場合も、補助的に hotelname/address を付与（無視される場合あり）
            if hotel_name:
                params['hotelname'] = hotel_name
            if address:
                params['address'] = address
        if check_in:
            params['checkin'] = check_in
        if check_out:
            params['checkout'] = check_out
        q = urlencode({ k:v for k,v in params.items() if v }, doseq=True)
        return f"{base}?{q}"
    except Exception:
        return None

def _normalize_booking_url(raw_url: str) -> str:
    """Booking.com のURLを STAY22 互換の安定した形式に正規化する。
    - ホストは booking.com のまま（サブドメイン許容）
    - 不要/短命なクエリ（utm/aid/label/メタGHA系）を除外
    - 主要な滞在条件のみを残す
    """
    try:
        parsed = urlparse(raw_url)
        host = (parsed.netloc or '').lower()
        if 'booking.com' not in host:
            return raw_url

        # 主要パラメータのみホワイトリスト
        allowed_keys = set([
            'checkin', 'checkout',
            'group_adults',
            'group_children',
            'no_rooms',
            'lang', 'selected_currency'
        ])

        # 除外したい接頭辞/キー
        blocked_prefixes = ('utm_',)
        blocked_keys = set([
            'aid', 'label', 'exrt', 'ext_price_total', 'ext_price_tax', 'xfc', 'hca',
            'edgtid', 'efpc', 'ts', 'efp', 'from_wishlist', 'dist', 'sb_price_type', 'srpvid',
            'req_adults', 'req_children', 'show_room'
        ])

        q_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        kept: list[tuple[str, str]] = []
        for k, v in q_pairs:
            kl = k.lower()
            if kl in allowed_keys:
                kept.append((k, v))
                continue
            if kl.startswith(blocked_prefixes) or kl in blocked_keys:
                continue
            # それ以外は捨てる（短命/計測系の可能性が高い）
            continue

        new_query = urlencode(kept, doseq=True)
        # スキームはhttps固定
        scheme = 'https'
        return urlunparse(parsed._replace(scheme=scheme, query=new_query))
    except Exception:
        return raw_url


def wrap_rakuten(raw_url: str, affiliate_id: Optional[str]) -> str:
    if not raw_url:
        return raw_url
    # Idempotency: already Rakuten affiliate domain
    try:
        parsed = urlparse(raw_url)
        if parsed.netloc.endswith("hb.afl.rakuten.co.jp"):
            return raw_url
    except Exception:
        pass
    if not affiliate_id:
        return raw_url
    base = f"https://hb.afl.rakuten.co.jp/hgc/{affiliate_id}/"
    pc = quote(raw_url, safe="")
    m = pc  # same as PC if mobile not provided
    return f"{base}?pc={pc}&m={m}&link_type=text"


def wrap_expedia_creator(raw_url: str, creator_id: Optional[str]) -> str:
    if not raw_url:
        return raw_url
    try:
        parsed = urlparse(raw_url)
        # If already on expedia affiliate wrapper, keep as is
        if parsed.netloc.endswith("expedia.com") and parsed.path.startswith("/affiliate/"):
            return raw_url
    except Exception:
        pass
    if not creator_id:
        return raw_url
    return f"https://expedia.com/affiliate/{creator_id}?url={quote(raw_url, safe='')}"


def wrap_agoda(raw_url: str, cid: Optional[str]) -> str:
    if not raw_url or not cid:
        return raw_url
    try:
        parsed = urlparse(raw_url)
        # Only apply for agoda domains
        if "agoda.com" not in (parsed.netloc or ""):
            return raw_url
        # Ensure cid param exists/updated
        return _append_params(raw_url, {"cid": cid})
    except Exception:
        return raw_url


def wrap_stay22(raw_url: str, aid: Optional[str]) -> str:
    if not raw_url:
        return raw_url
    try:
        parsed = urlparse(raw_url)
        # If already stay22 wrapper, keep
        if parsed.netloc.endswith("stay22.com") and parsed.path.startswith("/l/"):
            return raw_url
    except Exception:
        pass
    if not aid:
        return raw_url
    return f"https://www.stay22.com/l/{aid}?url={quote(raw_url, safe='')}"


# ValueCommerce は不使用（審査不承認のため無効化）


def wrap_a8(raw_url: str, a8mat: Optional[str]) -> str:
    """A8.net ラッパー。a8mat を使用して a8ejpredirect に生URLを渡す。
    参考: https://px.a8.net/svt/ejp?a8mat=XXXX+YYYY+ZZZZ+WWWW&a8ejpredirect=<ENCODED_URL>
    """
    if not raw_url or not a8mat:
        return raw_url
    try:
        parsed = urlparse(raw_url)
        # Idempotency: 既にA8リンクならそのまま
        if parsed.netloc.endswith("a8.net") or parsed.netloc.endswith("px.a8.net"):
            return raw_url
    except Exception:
        pass
    base = "https://px.a8.net/svt/ejp"
    # a8mat は '+' を含むフォーマットのため、エンコードせずそのまま渡す
    # a8ejpredirect のみURLエンコード（1回）
    return f"{base}?a8mat={a8mat}&a8ejpredirect={quote(raw_url, safe='')}"


def detect_platform_by_url(raw_url: str) -> Optional[str]:
    try:
        parsed = urlparse(raw_url)
        host = parsed.netloc or ""
        host_l = host.lower()
        if not host_l:
            return None
        if "booking.com" in host_l:
            return "booking"
        if "agoda.com" in host_l:
            return "agoda"
        if "expedia." in host_l or host_l.endswith("expedia.com"):
            return "expedia"
        if "rakuten.co.jp" in host_l and ("hotel.travel.rakuten.co.jp" in host_l or "travel.rakuten.co.jp" in host_l):
            return "rakuten"
        if "ikyu.com" in host_l:
            return "ikyu"
        if "jalan.net" in host_l:
            return "jalan"
        if "travel.yahoo.co.jp" in host_l:
            return "yahoo_travel"
        return None
    except Exception:
        return None


def apply_affiliate_wrapper(raw_url: str, provider_hint: Optional[str] = None) -> str:
    if not raw_url:
        return raw_url
    # Feature flag
    if (_cfg("AFF_WRAP_ENABLED", "true").lower() not in ["1", "true", "yes"]):
        return raw_url

    # まずURLから判定（最優先）。URLでわからない場合に限り、providerヒントを使用。
    platform = detect_platform_by_url(raw_url)
    if not platform and provider_hint:
        ph = (provider_hint or "").strip().lower()
        # ごく簡易な正規化
        if "booking" in ph:
            platform = "booking"
        elif "agoda" in ph:
            platform = "agoda"
        elif "expedia" in ph:
            platform = "expedia"
        elif "rakuten" in ph or "楽天" in ph:
            platform = "rakuten"
        elif "ikyu" in ph or "一休" in ph:
            platform = "ikyu"
        elif "jalan" in ph or "じゃらん" in ph:
            platform = "jalan"
        elif "yahoo" in ph:
            platform = "yahoo_travel"
    platform = (platform or "").lower()

    # Read env/config
    rakuten_aff = _cfg("RAKUTEN_AFFILIATE_ID")
    expedia_creator = _cfg("EXPEDIA_CREATOR_ID")
    agoda_cid = _cfg("AGODA_CID") or _cfg("AGODA_PARTNER_ID")  # backward compat
    stay22_aid = _cfg("STAY22_AID")
    # ValueCommerce は不使用
    vc_sid = None
    vc_pid = None
    vc_jalan_sid = None
    vc_jalan_pid = None
    vc_yahoo_sid = None
    vc_yahoo_pid = None
    # A8 per-advertiser a8mat
    a8_ikyu = _cfg("A8_IKYU_A8MAT")
    a8_jalan = _cfg("A8_JALAN_A8MAT")
    a8_yahoo = _cfg("A8_YAHOO_TRAVEL_A8MAT")

    try:
        if platform == "booking":
            # まずAllez方式で生成（lat/lng or hotelname/address は上位層からは渡ってこないため、URLからは抽出せず、単純化してSRPとして扱う）
            # URLからの厳密抽出は難しいため、当面は既存のBooking直URLをSTAY22パススルーにフォールバック
            normalized = _normalize_booking_url(raw_url)
            return wrap_stay22(normalized, stay22_aid)
        if platform == "agoda":
            return wrap_agoda(raw_url, agoda_cid)
        if platform == "expedia":
            return wrap_expedia_creator(raw_url, expedia_creator)
        if platform == "rakuten":
            return wrap_rakuten(raw_url, rakuten_aff)
        if platform == "ikyu":
            if a8_ikyu:
                return wrap_a8(raw_url, a8_ikyu)
            return raw_url
        if platform == "jalan":
            # A8のみ適用
            if a8_jalan:
                return wrap_a8(raw_url, a8_jalan)
            return raw_url
        if platform == "yahoo_travel":
            # A8のみ適用
            if a8_yahoo:
                return wrap_a8(raw_url, a8_yahoo)
            return raw_url
        # Unknown platform: leave as is
        return raw_url
    except Exception:
        return raw_url


def wrap_offers(offers: List[Dict]) -> List[Dict]:
    wrapped: List[Dict] = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        deeplink = o.get('deeplink')
        provider = o.get('provider')
        new_url = apply_affiliate_wrapper(deeplink, provider)
        nofollow_provider = provider  # unchanged
        new_item = dict(o)
        if new_url:
            new_item['deeplink'] = new_url
        wrapped.append(new_item)
    return wrapped


def apply_affiliate_wrapper_with_context(raw_url: str, provider_hint: Optional[str], spot: Optional[Any]) -> str:
    """コンテキスト（spot）を使ってより良いアフィリエイトリンクを生成。
    Booking.com は Allez を優先（lat/lng or hotelname+address, checkin/checkout）。
    """
    provider_hint_l = (provider_hint or '').lower() if provider_hint else ''
    is_booking = 'booking' in provider_hint_l or 'booking.com' in (urlparse(raw_url).netloc or '').lower()
    if is_booking:
        # クエリから日付抽出
        try:
            q = dict(parse_qsl(urlparse(raw_url).query, keep_blank_values=True))
            ci = q.get('checkin')
            co = q.get('checkout')
        except Exception:
            ci = None; co = None
        lat = getattr(spot, 'latitude', None) if spot is not None else None
        lng = getattr(spot, 'longitude', None) if spot is not None else None
        hotel_name = getattr(spot, 'name', None) if spot is not None else None
        address = None
        if spot is not None:
            address = getattr(spot, 'summary_location', None) or getattr(spot, 'location', None)
        allez = build_stay22_allez_for_booking(lat, lng, hotel_name, address, ci, co)
        if allez:
            return allez
    # フォールバック: 既存ロジック
    return apply_affiliate_wrapper(raw_url, provider_hint)


def wrap_offers_with_context(offers: List[Dict], spot: Any) -> List[Dict]:
    wrapped: List[Dict] = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        deeplink = o.get('deeplink')
        provider = o.get('provider')
        new_url = apply_affiliate_wrapper_with_context(deeplink, provider, spot)
        new_item = dict(o)
        if new_url:
            new_item['deeplink'] = new_url
        wrapped.append(new_item)
    return wrapped


