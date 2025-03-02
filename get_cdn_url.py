from app import create_app
from app.models import Spot
import os
import requests
import json

app = create_app()
with app.app_context():
    # 甲子園のスポット情報を取得（ID:5）
    spot = Spot.query.get(5)
    if not spot:
        print("Spot with ID 5 not found")
        exit(1)
    
    # Google Photo Referenceが有効な場合、CDN URLを取得
    if spot.google_photo_reference and spot.google_photo_reference != 'null' and spot.google_photo_reference != 'None':
        api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
        url = f"https://places.googleapis.com/v1/{spot.google_photo_reference}/media?skipHttpRedirect=true&maxHeightPx=400&maxWidthPx=400&key={api_key}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'photoUri' in data:
                        cdn_url = data['photoUri']
                        print(f"CDN URL: {cdn_url}")
                    else:
                        print("photoUri not found in response")
                except json.JSONDecodeError:
                    print("Failed to decode JSON response")
            else:
                print(f"API request failed with status code: {response.status_code}")
        except Exception as e:
            print(f"Error: {str(e)}")
    else:
        print("Invalid Google Photo Reference") 