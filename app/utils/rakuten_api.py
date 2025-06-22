import requests
import os
import logging
import html
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

def search_hotel(keyword, affiliate_id=None):
    """楽天トラベルAPIでホテルを検索する関数
    
    Args:
        keyword (str): 検索キーワード（ホテル名など）
        affiliate_id (str, optional): 楽天アフィリエイトID
        
    Returns:
        dict: APIレスポンス
    """
    api_key = os.environ.get('RAKUTEN_API_KEY')
    if not api_key:
        logger.error("楽天APIキーが設定されていません")
        return {"error": "楽天APIキーが設定されていません"}
    
    url = "https://app.rakuten.co.jp/services/api/Travel/KeywordHotelSearch/20170426"
    params = {
        "format": "json",
        "keyword": keyword,
        "applicationId": api_key,
        "hits": 5,  # 取得件数
        "responseType": "small"
    }
    
    # アフィリエイトIDが指定されている場合は追加
    if affiliate_id:
        params["affiliateId"] = affiliate_id
    
    try:
        print(f"楽天API呼び出し: URL={url}, パラメータ={params}")
        response = requests.get(url, params=params)
        response.raise_for_status()  # ステータスコードが200系以外の場合は例外を発生
        result = response.json()
        print(f"楽天API応答: {result.keys()}")
        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"楽天トラベルAPI呼び出しエラー: {str(e)}")
        return {"error": str(e)}

def generate_rakuten_affiliate_url(url, affiliate_id):
    """通常の楽天URLをアフィリエイトURLに変換する
    
    Args:
        url (str): 元のURL
        affiliate_id (str): 楽天アフィリエイトID
        
    Returns:
        str: アフィリエイトURL
    """
    if not affiliate_id or not url:
        print(f"アフィリエイトURL生成: パラメータ不足 - url={url}, affiliate_id={affiliate_id}")
        return url
    
    # HTMLエンコードを解除（&amp; → & など）
    decoded_url = html.unescape(url)
    print(f"アフィリエイトURL生成: 元URL={url}, デコード後={decoded_url}")
    
    # すでにアフィリエイトパラメータが含まれているか確認
    if f"af={affiliate_id}" in decoded_url:
        print(f"アフィリエイトURL生成: すでにアフィリエイトIDが含まれています")
        return decoded_url
    
    # URLにパラメータを追加
    separator = '&' if '?' in decoded_url else '?'
    result_url = f"{decoded_url}{separator}af={affiliate_id}"
    print(f"アフィリエイトURL生成: 結果={result_url}")
    return result_url 