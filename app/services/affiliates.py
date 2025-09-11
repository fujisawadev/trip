import os
from typing import Dict, List, Optional
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


def wrap_valuecommerce(raw_url: str, sid: Optional[str], pid: Optional[str]) -> str:
    if not raw_url or not sid or not pid:
        return raw_url
    # Idempotency: already vc referral
    try:
        parsed = urlparse(raw_url)
        if parsed.netloc.endswith("ck.jp.ap.valuecommerce.com"):
            return raw_url
    except Exception:
        pass
    base = "https://ck.jp.ap.valuecommerce.com/servlet/referral"
    vc_url = quote(raw_url, safe="")
    return f"{base}?sid={sid}&pid={pid}&vc_url={vc_url}"


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
    return f"{base}?a8mat={quote(a8mat, safe='')}&a8ejpredirect={quote(raw_url, safe='')}"


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
    vc_sid = _cfg("VC_SID")
    vc_pid = _cfg("VC_PID")
    # A8 per-advertiser a8mat
    a8_ikyu = _cfg("A8_IKYU_A8MAT")
    a8_jalan = _cfg("A8_JALAN_A8MAT")
    a8_yahoo = _cfg("A8_YAHOO_TRAVEL_A8MAT")

    try:
        if platform == "booking":
            return wrap_stay22(raw_url, stay22_aid)
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
            if a8_jalan:
                return wrap_a8(raw_url, a8_jalan)
            if vc_sid and vc_pid:
                return wrap_valuecommerce(raw_url, vc_sid, vc_pid)
            return raw_url
        if platform == "yahoo_travel":
            if a8_yahoo:
                return wrap_a8(raw_url, a8_yahoo)
            if vc_sid and vc_pid:
                return wrap_valuecommerce(raw_url, vc_sid, vc_pid)
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


