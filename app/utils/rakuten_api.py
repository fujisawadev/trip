import requests
import os
import logging
import html
import re
import json
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

logger = logging.getLogger(__name__)

# 楽天ホテルマッチング用閾値
RAKUTEN_MATCH_THRESHOLD = 70

def safe_decode_text(text):
    """安全な文字デコード処理 - 文字化けを検出・修正"""
    if not text:
        return text
    
    # 文字化け記号の検出
    if '�' in text:
        # 文字化けが含まれている場合の処理
        original_text = text
        
        # 文字化け記号を除去
        cleaned_text = text.replace('�', '')
        
        # 連続する空白を単一の空白に変換
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        logger.warning(f"文字化けを検出し修正: '{original_text}' -> '{cleaned_text}'")
        return cleaned_text
    
    return text

def validate_and_clean_keyword(keyword):
    """検索キーワードの検証とクリーンアップ"""
    if not keyword:
        return None
    
    # 文字化け修正
    cleaned_keyword = safe_decode_text(keyword)
    
    # 空白のみの場合は無効
    if not cleaned_keyword.strip():
        return None
    
    # 長すぎるキーワードは切り詰め
    if len(cleaned_keyword) > 100:
        cleaned_keyword = cleaned_keyword[:100]
        logger.warning(f"キーワードが長すぎるため切り詰めました: {len(keyword)} -> {len(cleaned_keyword)} 文字")
    
    return cleaned_keyword.strip()

def evaluate_hotel_candidates_with_llm(spot_name, hotel_candidates):
    """LLMを使用してホテル候補とスポット名のマッチ度を評価"""
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    if not openai_api_key:
        logger.warning("OpenAI API key not configured. LLM評価をスキップします")
        return None
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_api_key, timeout=30.0)
        
        candidates_text = []
        for i, hotel_item in enumerate(hotel_candidates):
            if 'hotel' in hotel_item and len(hotel_item['hotel']) > 0:
                hotel_info = hotel_item['hotel'][0]
                if 'hotelBasicInfo' in hotel_info:
                    basic_info = hotel_info['hotelBasicInfo']
                    hotel_name = basic_info.get('hotelName', '')
                    address = basic_info.get('address1', '') + basic_info.get('address2', '')
                    candidates_text.append(f"候補{i+1}: {hotel_name} - {address}")
        
        if not candidates_text:
            logger.warning("評価可能なホテル候補がありません")
            return None
        
        evaluation_prompt = f"""
        タスク: Instagram投稿で言及されたスポット名と楽天トラベル検索結果の適合性評価

        ## 分析対象
        - 対象スポット名: {spot_name}
        - 楽天トラベル検索候補:
        {chr(10).join(candidates_text)}

        ## 評価プロセス
        1. まず、対象スポット名の施設タイプを特定してください
        2. 次に、各楽天トラベル候補との関連性を評価してください
        3. 宿泊施設アフィリエイトとしての適切性を判定してください

        ## 施設タイプ分類
        - **宿泊施設**: ホテル、旅館、民宿、ゲストハウス、リゾート
        - **非宿泊施設**: 観光地、寺院、タワー、博物館、レストラン、カフェ、ショップ

        ## スコア付与基準
        - **90-100点**: 対象が宿泊施設で、候補と名称・所在地が高度に一致
        - **70-89点**: 対象が宿泊施設で、候補と相当の関連性がある
        - **30-69点**: 対象が宿泊施設だが、候補との関連性が限定的
        - **0-29点**: 対象が非宿泊施設、または関連性が認められない

        ## 重要原則
        観光地・飲食店等の非宿泊施設は、近隣ホテルが検索されても低スコア（0-29点）とし、
        宿泊予約アフィリエイトとしては不適切と判定してください。

        出力形式をJSON形式で返してください: {{"candidate1_score": 85, "candidate2_score": 45, "candidate3_score": 20, "best_candidate": 1, "explanation": "対象スポットの施設タイプと各候補との関連性に基づく評価理由"}}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "あなたはホテル検索結果の精度評価専門家です。スポット名とホテル候補の関連性を正確に評価してください。"},
                {"role": "user", "content": evaluation_prompt}
            ],
            max_tokens=300
        )
        
        content = response.choices[0].message.content
        evaluation_result = json.loads(content)
        
        logger.info(f"LLM評価完了: {evaluation_result}")
        return evaluation_result
        
    except Exception as e:
        logger.error(f"LLM評価エラー: {e}")
        return None

def select_best_hotel_with_evaluation(spot_name, hotel_results):
    """評価システム付きで最適なホテルを選択"""
    
    if not hotel_results.get('hotels'):
        logger.info(f"ホテル検索結果なし: {spot_name}")
        return None
    
    hotels = hotel_results['hotels'][:3]  # 上位3候補
    logger.info(f"ホテル候補数: {len(hotels)}件 for '{spot_name}'")
    
    if len(hotels) == 1:
        # 候補が1つの場合はLLM評価を実行
        evaluation = evaluate_hotel_candidates_with_llm(spot_name, hotels)
        if evaluation is None:
            # LLM評価に失敗した場合は従来通り最初の候補を採用
            logger.info(f"LLM評価失敗、従来方式で最初の候補を採用: {spot_name}")
            return hotels[0]
        
        candidate1_score = evaluation.get('candidate1_score', 0)
        if candidate1_score >= RAKUTEN_MATCH_THRESHOLD:
            logger.info(f"ホテル候補を採用: スコア={candidate1_score}, スポット='{spot_name}'")
            return hotels[0]
        else:
            logger.info(f"ホテル候補のマッチ度が閾値未満: スコア={candidate1_score}, 閾値={RAKUTEN_MATCH_THRESHOLD}, スポット='{spot_name}'")
            return None
    
    # 複数候補の場合はLLM評価で最適候補を選択
    evaluation = evaluate_hotel_candidates_with_llm(spot_name, hotels)
    if evaluation is None:
        # LLM評価に失敗した場合は従来通り最初の候補を採用
        logger.info(f"LLM評価失敗、従来方式で最初の候補を採用: {spot_name}")
        return hotels[0]
    
    # best_candidateがNoneの場合を適切に処理
    best_candidate = evaluation.get('best_candidate')
    if best_candidate is None:
        logger.info(f"LLM評価により適切な候補なし: スポット='{spot_name}'")
        return None
    
    best_candidate_idx = best_candidate - 1  # 1-indexedを0-indexedに変換
    best_score = evaluation.get(f'candidate{best_candidate_idx + 1}_score', 0)
    explanation = evaluation.get('explanation', '')
    
    if 0 <= best_candidate_idx < len(hotels) and best_score >= RAKUTEN_MATCH_THRESHOLD:
        logger.info(f"ホテル候補を採用: 候補{best_candidate_idx + 1}, スコア={best_score}, 説明='{explanation}', スポット='{spot_name}'")
        return hotels[best_candidate_idx]
    else:
        logger.info(f"全ホテル候補が閾値未満: 最高スコア={best_score}, 閾値={RAKUTEN_MATCH_THRESHOLD}, スポット='{spot_name}'")
        return None

def search_hotel(keyword, affiliate_id=None):
    """楽天トラベルAPIでホテルを検索する関数
    
    Args:
        keyword (str): 検索キーワード（ホテル名など）
        affiliate_id (str, optional): 楽天アフィリエイトID
        
    Returns:
        dict: APIレスポンス
    """
    # キーワードの検証とクリーンアップ
    cleaned_keyword = validate_and_clean_keyword(keyword)
    if not cleaned_keyword:
        logger.warning(f"無効なキーワード: '{keyword}'")
        return {
            "error": "invalid_keyword",
            "message": "検索キーワードが無効です",
            "keyword": keyword
        }
    
    api_key = os.environ.get('RAKUTEN_API_KEY')
    if not api_key:
        logger.error("楽天APIキーが設定されていません")
        return {"error": "api_key_missing", "message": "楽天APIキーが設定されていません"}
    
    url = "https://app.rakuten.co.jp/services/api/Travel/KeywordHotelSearch/20170426"
    params = {
        "format": "json",
        "keyword": cleaned_keyword,  # クリーンアップされたキーワードを使用
        "applicationId": api_key,
        "hits": 3,  # 取得件数（LLM評価用に最適化）
        "responseType": "small"
    }
    
    # アフィリエイトIDが指定されている場合は追加
    if affiliate_id:
        params["affiliateId"] = affiliate_id
    
    try:
        print(f"楽天API呼び出し: URL={url}, パラメータ={params}")
        response = requests.get(url, params=params, timeout=30)
        
        # HTTPエラーの詳細な処理
        if response.status_code == 404:
            logger.info(f"楽天API: ホテルが見つかりませんでした - キーワード: '{keyword}'")
            return {
                "error": "no_hotels_found", 
                "message": "該当するホテルが見つかりませんでした",
                "keyword": keyword,
                "hotels": []  # 空のホテルリストを返す
            }
        elif response.status_code == 429:
            logger.warning(f"楽天API: レート制限に達しました")
            return {
                "error": "rate_limit_exceeded",
                "message": "楽天APIのレート制限に達しました。しばらく時間をおいて再度お試しください"
            }
        elif response.status_code == 403:
            logger.error(f"楽天API: アクセス権限エラー")
            return {
                "error": "access_forbidden",
                "message": "楽天APIへのアクセスが拒否されました。APIキーを確認してください"
            }
        elif response.status_code >= 500:
            logger.error(f"楽天API: サーバーエラー {response.status_code}")
            return {
                "error": "server_error",
                "message": "楽天APIサーバーでエラーが発生しています。しばらく時間をおいて再度お試しください"
            }
        elif response.status_code != 200:
            logger.error(f"楽天API: HTTPエラー {response.status_code}")
            return {
                "error": "http_error",
                "message": f"楽天APIでHTTPエラーが発生しました (ステータス: {response.status_code})"
            }
        
        # 正常レスポンスの処理
        result = response.json()
        print(f"楽天API応答: {result.keys()}")
        
        # APIレスポンスにエラーが含まれているかチェック
        if 'error' in result:
            error_message = result.get('error', 'Unknown API error')
            logger.error(f"楽天API応答エラー: {error_message}")
            return {
                "error": "api_response_error",
                "message": f"楽天APIエラー: {error_message}"
            }
        
        # ホテルが見つからない場合（正常レスポンスだが結果が空）
        hotels = result.get('hotels', [])
        if not hotels:
            logger.info(f"楽天API: 検索結果が0件でした - キーワード: '{keyword}'")
            return {
                "error": "no_hotels_found",
                "message": "該当するホテルが見つかりませんでした",
                "keyword": keyword,
                "hotels": []
            }
        
        return result
        
    except requests.exceptions.Timeout:
        logger.error(f"楽天API: タイムアウトエラー")
        return {
            "error": "timeout_error",
            "message": "楽天APIへの接続がタイムアウトしました"
        }
    except requests.exceptions.ConnectionError:
        logger.error(f"楽天API: 接続エラー")
        return {
            "error": "connection_error",
            "message": "楽天APIへの接続に失敗しました"
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"楽天トラベルAPI呼び出しエラー: {str(e)}")
        return {
            "error": "request_error",
            "message": f"楽天APIリクエストエラー: {str(e)}"
        }
    except Exception as e:
        logger.error(f"楽天API予期しないエラー: {str(e)}")
        return {
            "error": "unexpected_error",
            "message": f"予期しないエラーが発生しました: {str(e)}"
        }

def generate_rakuten_affiliate_url(url, affiliate_id):
    """通常の楽天URLをアフィリエイトURLに変換する（安全版）
    
    Args:
        url (str): 元のURL
        affiliate_id (str): 楽天アフィリエイトID
        
    Returns:
        str: アフィリエイトURL
    """
    if not affiliate_id or not url:
        print(f"アフィリエイトURL生成: パラメータ不足 - url={url}, affiliate_id={affiliate_id}")
        return url
    
    try:
        # 文字化けチェック・修正
        cleaned_url = safe_decode_text(url)
        if cleaned_url != url:
            print(f"アフィリエイトURL生成: 文字化けを修正 - 元URL={url}, 修正後={cleaned_url}")
            url = cleaned_url
        
        # HTMLエンコードを解除（&amp; → & など）
        decoded_url = html.unescape(url)
        print(f"アフィリエイトURL生成: 元URL={url}, デコード後={decoded_url}")
        
        # URLを安全にパース
        try:
            parsed = urlparse(decoded_url)
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            
            # アフィリエイトIDを追加（重複チェック込み）
            query_params['af'] = [affiliate_id]
            
            # 安全にURL再構築
            new_query = urlencode(query_params, doseq=True)
            result_url = urlunparse(parsed._replace(query=new_query))
            
            print(f"アフィリエイトURL生成: 結果={result_url}")
            return result_url
            
        except Exception as parse_error:
            # URLパースに失敗した場合は従来の方法にフォールバック
            logger.warning(f"URLパースに失敗、従来方法を使用: {parse_error}")
            
            # すでにアフィリエイトパラメータが含まれているか確認
            if f"af={affiliate_id}" in decoded_url:
                print(f"アフィリエイトURL生成: すでにアフィリエイトIDが含まれています")
                return decoded_url
            
            # URLにパラメータを追加
            separator = '&' if '?' in decoded_url else '?'
            result_url = f"{decoded_url}{separator}af={affiliate_id}"
            print(f"アフィリエイトURL生成: 結果={result_url}")
            return result_url
            
    except Exception as e:
        logger.error(f"アフィリエイトURL生成エラー: {e}")
        print(f"アフィリエイトURL生成: エラーのため元URLを返します - {e}")
        return url  # エラー時は元URLをそのまま返す 