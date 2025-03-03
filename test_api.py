from app import create_app
import json

app = create_app()

with app.test_client() as client:
    # APIエンドポイントにリクエストを送信
    response = client.get('/api/spots/1')
    
    # レスポンスの内容を表示
    print(f'ステータスコード: {response.status_code}')
    print(f'レスポンスヘッダー: {response.headers}')
    
    if response.data:
        try:
            data = json.loads(response.data)
            print('レスポンスデータ:')
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # affiliate_linksの確認
            affiliate_links = data.get('affiliate_links', [])
            print(f'\nアフィリエイトリンク数: {len(affiliate_links)}')
            for link in affiliate_links:
                print(f"- ID:{link.get('id')}, Platform:{link.get('platform')}, Title:{link.get('title')}, is_active:{link.get('is_active', 'N/A')}")
        except json.JSONDecodeError:
            print(f'JSONデコードエラー: {response.data.decode()[:200]}...')
    else:
        print('レスポンスデータなし') 