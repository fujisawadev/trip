from app import create_app
from app.models import User, Spot
import requests
from flask import url_for

app = create_app()
with app.app_context():
    # ユーザーID 1のプロフィール情報を取得
    user = User.query.get(1)
    if not user:
        print("User with ID 1 not found")
        exit(1)
    
    print(f"User: {user.username} (ID: {user.id})")
    
    # ユーザーID 1のスポット一覧を取得
    spots = Spot.query.filter_by(user_id=1, is_active=True).all()
    print(f"Total spots: {len(spots)}")
    
    # スポットID 5（甲子園）が含まれているか確認
    koshien = None
    for spot in spots:
        print(f"Spot ID: {spot.id}, Name: {spot.name}")
        if spot.id == 5:
            koshien = spot
    
    if koshien:
        print("\nKoshien Stadium found:")
        print(f"ID: {koshien.id}")
        print(f"Name: {koshien.name}")
        print(f"Google Place ID: {koshien.google_place_id}")
        print(f"Google Photo Reference: {koshien.google_photo_reference}")
        
        # 写真情報を確認
        print("\nPhotos:")
        if hasattr(koshien, 'photos') and koshien.photos:
            for i, photo in enumerate(koshien.photos):
                print(f"Photo {i+1}: {photo.photo_url}")
        else:
            print("No photos found")
        
        # テンプレートで生成されるURLを確認
        with app.test_request_context():
            if koshien.google_photo_reference and koshien.google_photo_reference != 'null' and koshien.google_photo_reference != 'None':
                proxy_url = url_for('public.photo_proxy', photo_reference=koshien.google_photo_reference)
                print(f"\nProxy URL that would be generated in template: {proxy_url}")
            else:
                print("\nNo valid Google Photo Reference for proxy URL")
    else:
        print("\nKoshien Stadium (ID: 5) not found in user's spots") 