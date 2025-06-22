import requests
import os
import logging
import html
from urllib.parse import urlencode
import difflib

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

def similar_text(str1, str2, min_similarity=0.5):
    """2つの文字列の類似度を判定する関数（簡易版）
    
    Args:
        str1 (str): 比較する文字列1
        str2 (str): 比較する文字列2
        min_similarity (float): 類似とみなす最小値（0.0～1.0）
        
    Returns:
        bool: 類似しているかどうか
    """
    if not str1 or not str2:
        print(f"類似度判定: 空文字列があります - str1={str1}, str2={str2}")
        return False
    
    # 全角カタカナ・英数字を半角に変換する関数
    def normalize_text(text):
        import unicodedata
        import re
        # 全角→半角変換（カタカナ以外）
        text = unicodedata.normalize('NFKC', text)
        # 空白文字を統一（\u3000 = 全角スペース、\t = タブなど）
        text = re.sub(r'[\s\u3000]+', ' ', text)
        # 記号類を除去（オプション：記号が一致判定に影響する場合）
        # text = re.sub(r'[^\w\s]', '', text)
        # 前後の空白を削除し、小文字に変換
        return text.strip().lower()
    
    # 正規化して小文字に変換して比較
    s1 = normalize_text(str1)
    s2 = normalize_text(str2)
    
    print(f"類似度判定: 正規化後 - s1='{s1}', s2='{s2}'")
    
    # どちらかの文字列がもう一方を含む場合は類似と判定
    if s1 in s2 or s2 in s1:
        print(f"類似度判定: 部分一致しました - '{s1}' と '{s2}'")
        return True
    
    # 各単語ごとに一致する単語の割合で判定
    words1 = set(s1.split())
    words2 = set(s2.split())
    
    # 単語が少なすぎる場合は、文字ベースの類似度判定にフォールバック
    if len(words1) < 2 or len(words2) < 2:
        print(f"類似度判定: 単語数が少ないため文字ベースで比較します - s1='{s1}', s2='{s2}'")
        # SequenceMatcherで文字列全体の類似度を計算
        seq_matcher = difflib.SequenceMatcher(None, s1, s2)
        char_similarity = seq_matcher.ratio()
        print(f"類似度判定: 文字ベースの類似度={char_similarity}, 閾値=0.6")
        return char_similarity >= 0.6
    
    # 共通する単語の割合
    common_words = words1.intersection(words2)
    similarity = len(common_words) / max(len(words1), len(words2))
    
    print(f"類似度判定: 共通単語={common_words}, 類似度={similarity}, 閾値={min_similarity}")
    return similarity >= min_similarity 