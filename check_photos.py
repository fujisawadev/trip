from app import create_app, db
from app.models import Photo

def check_photos():
    """データベース内のGoogle写真情報を確認する"""
    app = create_app()
    with app.app_context():
        # Google写真を取得
        photos = Photo.query.filter(Photo.is_google_photo == True).all()
        
        print(f'Google写真の数: {len(photos)}件')
        
        # 最初の3件を表示
        for photo in photos[:3]:
            print(f'ID: {photo.id}, spot_id: {photo.spot_id}')
            print(f'photo_url: {photo.photo_url[:100]}...' if photo.photo_url else 'photo_url: None')
            print(f'google_photo_reference: {photo.google_photo_reference[:30]}...' if photo.google_photo_reference else 'google_photo_reference: None')
            print('-' * 50)

if __name__ == "__main__":
    check_photos() 