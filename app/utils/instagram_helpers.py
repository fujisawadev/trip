from urllib.parse import urlparse, parse_qs

def extract_cursor_from_url(url):
    """URLからafterパラメータを抽出する"""
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        
        if 'after' in query_params:
            return query_params['after'][0]
        
        return None
    except:
        return None 