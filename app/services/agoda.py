import os
from typing import Any, Dict, Optional
import requests
from flask import current_app


def _cfg(key: str, default: Optional[str] = None) -> Optional[str]:
    return current_app.config.get(key) if current_app else os.environ.get(key, default)


def build_deeplink(agoda_hotel_id: Optional[str], check_in: str, check_out: str,
                   adults: int, children: int = 0,
                   cid: Optional[str] = None, campaign_id: Optional[str] = None,
                   locale: str = 'ja-jp', currency: str = 'JPY', sub_id: Optional[str] = None) -> str:
    base = 'https://www.agoda.com/partners/partnersearch.aspx'
    params: Dict[str, Any] = {
        'checkIn': check_in,
        'checkOut': check_out,
        'NumberofAdults': adults,
        'NumberofChildren': max(0, int(children) if children is not None else 0),
        'Rooms': 1,
        'currencyCode': currency,
        'locale': locale,
    }
    if cid: params['cid'] = cid
    if campaign_id: params['campaignid'] = campaign_id
    if agoda_hotel_id: params['hid'] = agoda_hotel_id
    if sub_id: params['tag'] = sub_id
    query = '&'.join([f"{k}={v}" for k, v in params.items()])
    return f"{base}?{query}"


def fetch_price(hotel_id: str, check_in: str, check_out: str, adults: int,
                locale: str, currency: str, sub_id: Optional[str]) -> Optional[Dict[str, Any]]:
    url = _cfg('AGODA_AFFILIATE_LITE_URL') or _cfg('AGODA_API_BASE')
    api_key = _cfg('AGODA_API_KEY')
    site_id = _cfg('AGODA_SITE_ID')
    if not url or not api_key or not site_id:
        return None
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip,deflate',
        'Content-Type': 'application/json',
        'Authorization': f'{site_id}:{api_key}',
    }
    payload = {
        'criteria': {
            'additional': {
                'currency': currency,
                'language': locale,
                'discountOnly': False,
                'occupancy': {
                    'numberOfAdult': adults,
                    'numberOfChildren': 0
                }
            },
            'checkInDate': check_in,
            'checkOutDate': check_out,
            'hotelId': [int(hotel_id)] if str(hotel_id).isdigit() else [hotel_id]
        }
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json() if resp.content else None
        results = data.get('results') if isinstance(data, dict) else []
        if not results:
            return None
        first = results[0]
        return {
            'price': first.get('dailyRate'),
            'currency': first.get('currency', currency),
            'deeplink': first.get('landingURL')
        }
    except Exception:
        return None


