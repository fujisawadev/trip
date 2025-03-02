from app import create_app
from app.models import Spot
import requests
import urllib.parse

app = create_app()
with app.app_context():
    # 甲子園のスポット情報を取得（ID:5）
    spot = Spot.query.get(5)
    if not spot:
        print("Spot with ID 5 not found")
        exit(1)
    
    # Google Photo Referenceを取得
    photo_reference = spot.google_photo_reference
    print(f"Photo Reference: {photo_reference}")
    
    if photo_reference and photo_reference != 'null' and photo_reference != 'None':
        # プロキシエンドポイントのURLを構築
        encoded_reference = urllib.parse.quote(photo_reference)
        proxy_url = f"http://127.0.0.1:5000/photo_proxy/{encoded_reference}"
        print(f"Proxy URL: {proxy_url}")
        
        # プロキシエンドポイントにリクエストを送信
        try:
            response = requests.get(proxy_url, allow_redirects=False)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 302:  # リダイレクト
                redirect_url = response.headers.get('Location')
                print(f"Redirect URL: {redirect_url}")
                
                # リダイレクト先にアクセスできるか確認
                redirect_response = requests.head(redirect_url)
                print(f"Redirect Status: {redirect_response.status_code}")
            else:
                print(f"Response Headers: {response.headers}")
                print(f"Response Content: {response.text[:200]}...")
        except Exception as e:
            print(f"Error: {str(e)}")
    else:
        print("Invalid Google Photo Reference") 