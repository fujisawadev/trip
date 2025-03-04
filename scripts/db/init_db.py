import os
import sys
import json

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app, db
from app.models import User, Spot, Photo, SocialAccount, AffiliateLink, SocialPost

app = create_app()

def init_db():
    with app.app_context():
        # データベースの初期化
        db.drop_all()  # 既存のテーブルをすべて削除
        db.create_all()  # テーブルを新規作成
        
        print("データベースを初期化しました。")
        
        # テストユーザーの作成
        test_user = User(
            username="testuser",
            email="test@example.com",
            bio="This is a test user account.",
            profile_pic_url="default_profile.jpg",
            spots_heading="My Favorite Places"
        )
        test_user.set_password("password123")
        db.session.add(test_user)
        db.session.flush()  # IDを生成するためにフラッシュ
        
        # ソーシャルアカウントの追加
        social = SocialAccount(
            user_id=test_user.id,
            instagram="testuser",
            twitter="testuser",
            tiktok="testuser",
            youtube="https://youtube.com/testuser"
        )
        db.session.add(social)
        
        # 東京のサンプルスポット
        spot1 = Spot(
            user_id=test_user.id,
            name="Test Cafe",
            location="Tokyo, Japan",
            description="A cozy cafe with great coffee and atmosphere.",
            category="カフェ",
            is_active=True,
            # 地図情報
            latitude=35.6812362,
            longitude=139.7671248,
            # Google Places API関連情報
            google_place_id="ChIJG1YiXK-MGGAR5-3EYQpkOZM",
            formatted_address="〒100-0006 東京都千代田区有楽町1丁目",
            types=json.dumps(["cafe", "food", "point_of_interest", "establishment"]),
            thumbnail_url="https://example.com/images/test_cafe_thumb.jpg",
            google_photo_reference="Aap_uEDxzTK1fuAZzLDvJ6Q3ZB6Ur2FQiE4xIE-bXDdcYjDkBKrv8",
            summary_location="東京都千代田区",
            google_maps_url="https://www.google.com/maps/search/?api=1&query=Test+Cafe+Tokyo&query_place_id=ChIJG1YiXK-MGGAR5-3EYQpkOZM"
        )
        
        # 京都のサンプルスポット
        spot2 = Spot(
            user_id=test_user.id,
            name="Sakura Park",
            location="Kyoto, Japan",
            description="Beautiful park with cherry blossoms in spring.",
            category="公園",
            is_active=True,
            # 地図情報
            latitude=35.0116,
            longitude=135.7681,
            # Google Places API関連情報
            google_place_id="ChIJ8cM8zdaoAWARPR27azYdlsA",
            formatted_address="〒606-8354 京都府京都市左京区",
            types=json.dumps(["park", "tourist_attraction", "point_of_interest"]),
            thumbnail_url="https://example.com/images/sakura_park_thumb.jpg",
            google_photo_reference="Aap_uECyMSZzvIFAyoX7J9n-h0bLmb9CBZjgHPEbQbkZQG-Qr0",
            summary_location="京都府京都市左京区",
            google_maps_url="https://www.google.com/maps/search/?api=1&query=Sakura+Park+Kyoto&query_place_id=ChIJ8cM8zdaoAWARPR27azYdlsA"
        )
        
        db.session.add(spot1)
        db.session.add(spot2)
        db.session.flush()  # IDを生成するためにフラッシュ
        
        # 写真の追加
        photo1 = Photo(
            spot_id=spot1.id,
            photo_url="uploads/test_cafe_1.jpg",
            is_google_photo=False
        )
        
        photo2 = Photo(
            spot_id=spot1.id,
            google_photo_reference="Aap_uEDxzTK1fuAZzLDvJ6Q3ZB6Ur2FQiE4xIE-bXDdcYjDkBKrv8",
            is_google_photo=True
        )
        
        photo3 = Photo(
            spot_id=spot2.id,
            photo_url="uploads/sakura_park_1.jpg",
            is_google_photo=False
        )
        
        db.session.add(photo1)
        db.session.add(photo2)
        db.session.add(photo3)
        
        # アフィリエイトリンクの追加
        affiliate_links = [
            AffiliateLink(
                spot_id=spot1.id,
                platform="booking",
                url="https://www.booking.com/hotel/jp/test-cafe.html?aid=1234",
                title="Booking.com",
                description="最低価格保証・無料キャンセル",
                logo_url="https://cdn.builder.io/api/v1/image/assets/b8fa2d7a435f48ebab0c12e03b54941b/84944c1def9ac6fe8cdcddc26dbd5fcdc7e1ec4701a8ccece74cbd6a2b688715",
                icon_key="booking-com"
            ),
            AffiliateLink(
                spot_id=spot1.id,
                platform="rakuten",
                url="https://travel.rakuten.co.jp/hotel/japan/tokyo/test-cafe/?f_no=1234",
                title="楽天トラベル",
                description="楽天ポイントが貯まる・使える",
                logo_url="https://cdn.builder.io/api/v1/image/assets/b8fa2d7a435f48ebab0c12e03b54941b/532d34cb618a990f64da51d78f6168753a428877874b771849ef370903a1d740",
                icon_key="rakuten-travel"
            ),
            AffiliateLink(
                spot_id=spot2.id,
                platform="jalan",
                url="https://www.jalan.net/yad123456/",
                title="じゃらん",
                description="最大10%ポイント還元",
                logo_url="",
                icon_key="jalan"
            )
        ]
        
        for link in affiliate_links:
            db.session.add(link)
        
        # SNS投稿の追加
        social_posts = [
            SocialPost(
                user_id=test_user.id,
                spot_id=spot1.id,
                platform="instagram",
                post_url="https://www.instagram.com/p/abcdefg/",
                post_id="abcdefg",
                thumbnail_url="https://cdn.builder.io/api/v1/image/assets/b8fa2d7a435f48ebab0c12e03b54941b/c4b6eceea17bf421958ffab803902982674183dbd0877d7757c20a985ff83966",
                caption="Test Cafeでの素敵な時間 #testcafe #tokyo"
            ),
            SocialPost(
                user_id=test_user.id,
                spot_id=spot2.id,
                platform="twitter",
                post_url="https://twitter.com/user/status/123456789",
                post_id="123456789",
                thumbnail_url="https://cdn.builder.io/api/v1/image/assets/b8fa2d7a435f48ebab0c12e03b54941b/6b633b68e920d2d541c15dfbc0f06ca6e1a326e984e57cf41fc1f7a9a6582368",
                caption="京都の桜公園は最高！ #sakurapark #kyoto"
            )
        ]
        
        for post in social_posts:
            db.session.add(post)
        
        db.session.commit()
        
        print("テストユーザーとサンプルデータを作成しました。")
        print("ログイン情報: email=test@example.com, password=password123")
        print(f"作成されたデータ:")
        print(f"- スポット: {Spot.query.count()}件")
        print(f"- 写真: {Photo.query.count()}件")
        print(f"- アフィリエイトリンク: {AffiliateLink.query.count()}件")
        print(f"- SNS投稿: {SocialPost.query.count()}件")

if __name__ == "__main__":
    init_db() 