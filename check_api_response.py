import sys
import requests
import json

# APIエンドポイントからスポット詳細を取得
response = requests.get('http://localhost:5000/api/spots/1')
data = response.json()

# レスポンスの内容を表示
print('API Response Status:', response.status_code)
print('Spot Name:', data.get('name', 'N/A'))

# affiliate_linksの確認
affiliate_links = data.get('affiliate_links', [])
print('Affiliate Links Count:', len(affiliate_links))
for link in affiliate_links:
    print(f"- ID:{link.get('id')}, Platform:{link.get('platform')}, Title:{link.get('title')}, is_active:{link.get('is_active', 'N/A')}")

# 全レスポンスをJSON形式で表示
print('\nFull Response:')
print(json.dumps(data, indent=2, ensure_ascii=False)) 