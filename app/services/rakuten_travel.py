import os
from typing import Any, Dict, Optional
import requests
from flask import current_app

from app.utils.rakuten_api import generate_rakuten_affiliate_url


def _cfg(key: str, default: Optional[str] = None) -> Optional[str]:
    return current_app.config.get(key) if current_app else os.environ.get(key, default)


def _api_key() -> Optional[str]:
    return os.environ.get('RAKUTEN_API_KEY')


def _affiliate_id() -> Optional[str]:
    return _cfg('RAKUTEN_AFFILIATE_ID') or os.environ.get('RAKUTEN_AFFILIATE_ID')


def _get(url: str, params: Dict[str, Any], timeout: float = 12.0) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def fetch_detail_by_hotel_no(hotel_no: str) -> Optional[Dict[str, Any]]:
    api_key = _api_key()
    if not api_key or not hotel_no:
        return None
    url = 'https://app.rakuten.co.jp/services/api/Travel/HotelDetailSearch/20170426'
    params = {
        'format': 'json',
        'applicationId': api_key,
        'hotelNo': hotel_no,
        'responseType': 'small'
    }
    return _get(url, params)


def simple_hotel_search_by_geo(keyword: str, latitude: float, longitude: float, hits: int = 5) -> Optional[Dict[str, Any]]:
    """Rakuten Travel SimpleHotelSearch with lat/lng and keyword (formatVersion=2).
    Returns raw response dict or None.
    """
    api_key = _api_key()
    if not api_key or not keyword or latitude is None or longitude is None:
        return None
    url = 'https://app.rakuten.co.jp/services/api/Travel/SimpleHotelSearch/20170426'
    params = {
        'applicationId': api_key,
        'format': 'json',
        'formatVersion': 2,
        'keyword': keyword,
        'latitude': latitude,
        'longitude': longitude,
        'datumType': 1,
        'hits': hits,
    }
    return _get(url, params)


def fetch_vacant_price_by_hotel_no(hotel_no: str, check_in: str, check_out: str, adults: int) -> Optional[Dict[str, Any]]:
    """Try to get date-specific price via VacantHotelSearch. Fallback to None on error.
    Note: 'hotelNo' filter support may vary; handle gracefully.
    """
    api_key = _api_key()
    if not api_key or not hotel_no:
        return None
    url = 'https://app.rakuten.co.jp/services/api/Travel/VacantHotelSearch/20170426'
    params = {
        'format': 'json',
        'applicationId': api_key,
        'checkinDate': check_in,
        'checkoutDate': check_out,
        'adultNum': max(1, int(adults or 1)),
        'roomNum': 1,
        'hits': 1,
        'responseType': 'small',
        'hotelNo': hotel_no,
    }
    data = _get(url, params)
    if not data:
        return None
    hotels = data.get('hotels') or []
    if not hotels:
        return None

    best_total = None
    best_charge = None
    deeplink = None

    # VacantHotelSearch typically returns per-room prices under roomInfo.dailyCharge
    for h in hotels:
        if not isinstance(h, dict) or 'hotel' not in h or not h['hotel']:
            continue
        hotel_nodes = h['hotel']
        basic_info = {}
        for node in hotel_nodes:
            if not isinstance(node, dict):
                continue
            if 'hotelBasicInfo' in node:
                basic_info = node.get('hotelBasicInfo') or {}
            if 'roomInfo' in node:
                room_info = node.get('roomInfo')
                # roomInfo may be list or dict
                room_list = room_info if isinstance(room_info, list) else [room_info]
                for r in room_list:
                    if not isinstance(r, dict):
                        continue
                    daily = r.get('dailyCharge') or {}
                    # Prefer total if present; fallback to rakutenCharge
                    total_val = daily.get('total')
                    charge_val = daily.get('rakutenCharge')
                    try:
                        if total_val is not None:
                            t = float(total_val)
                            best_total = t if best_total is None or t < best_total else best_total
                        if charge_val is not None:
                            c = float(charge_val)
                            best_charge = c if best_charge is None or c < best_charge else best_charge
                    except Exception:
                        continue
        if not deeplink and basic_info:
            url0 = basic_info.get('hotelInformationUrl')
            if url0:
                deeplink = generate_rakuten_affiliate_url(url0, _affiliate_id())

    price = best_total if best_total is not None else best_charge
    if price is None:
        # Fallback to basic min charge when no dailyCharge present
        try:
            first = hotels[0]
            info = first['hotel'][0].get('hotelBasicInfo', {}) if isinstance(first, dict) and first.get('hotel') else {}
            if info:
                price = info.get('hotelMinCharge') or info.get('hotelMinChargeForStay')
                if not deeplink and info.get('hotelInformationUrl'):
                    deeplink = generate_rakuten_affiliate_url(info.get('hotelInformationUrl'), _affiliate_id())
        except Exception:
            pass

    if price is not None or deeplink:
        return {
            'price': price,
            'currency': 'JPY',
            'deeplink': deeplink,
        }
    return None


def build_offer_from_hotel_no(hotel_no: str, check_in: str, check_out: str, adults: int) -> Optional[Dict[str, Any]]:
    # price取得（可能な限り日付依存）
    vacant = fetch_vacant_price_by_hotel_no(hotel_no, check_in, check_out, adults)

    # deeplink生成（必ず日付・人数を付与）
    def _build_dated_deeplink(hotel_no_str: str) -> Optional[str]:
        try:
            from datetime import datetime
            ci = datetime.strptime(check_in, '%Y-%m-%d')
            co = datetime.strptime(check_out, '%Y-%m-%d')
            y1, m1, d1 = ci.year, ci.month, ci.day
            y2, m2, d2 = co.year, co.month, co.day
            base = f"https://hotel.travel.rakuten.co.jp/hotelinfo/plan/{hotel_no_str}"
            params = (
                f"f_flg=PLAN&f_nen1={y1}&f_tuki1={m1}&f_hi1={d1}"
                f"&f_nen2={y2}&f_tuki2={m2}&f_hi2={d2}"
                f"&f_heya_su=1&f_otona_su={max(1, int(adults or 1))}&s_id=0"
            )
            url_with_params = f"{base}?{params}"
            return generate_rakuten_affiliate_url(url_with_params, _affiliate_id())
        except Exception:
            return None

    detail = fetch_detail_by_hotel_no(hotel_no)
    deeplink = _build_dated_deeplink(str(hotel_no))

    price_val = vacant.get('price') if vacant else None
    if price_val is None and detail and isinstance(detail, dict):
        try:
            hotels = detail.get('hotels') or []
            if hotels and isinstance(hotels[0], dict) and hotels[0].get('hotel'):
                info = hotels[0]['hotel'][0].get('hotelBasicInfo', {})
                price_val = info.get('hotelMinCharge') or info.get('hotelMinChargeForStay')
        except Exception:
            pass

    if price_val is not None or deeplink:
        return {
            'provider': '楽天トラベル',
            'price': price_val,
            'currency': 'JPY',
            'deeplink': deeplink,
            'is_min_price': False,
        }
    return None


