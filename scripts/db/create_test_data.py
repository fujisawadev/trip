import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app, db
from app.models import User, Spot, Photo, SocialAccount, AffiliateLink, SocialPost

app = create_app()

def create_test_data():
    with app.app_context():
        # テストユーザーを取得
        test_user = User.query.filter_by(username="testuser").first()
        if not test_user:
            print("テストユーザーが見つかりません。先にinit_db.pyを実行してください。")
            return
        
        # テストスポットを取得
        test_spot = Spot.query.filter_by(name="Test Cafe").first()
        if not test_spot:
            print("テストスポットが見つかりません。先にinit_db.pyを実行してください。")
            return
        
        # Google Maps URLを追加
        test_spot.google_maps_url = "https://www.google.com/maps/search/?api=1&query=Test+Cafe+Tokyo"
        
        # アフィリエイトリンクを追加
        affiliate_links = [
            AffiliateLink(
                spot_id=test_spot.id,
                platform="booking",
                url="https://www.booking.com/hotel/jp/test-cafe.html?aid=1234",
                title="Booking.com",
                description="最低価格保証・無料キャンセル",
                logo_url="https://cdn.builder.io/api/v1/image/assets/b8fa2d7a435f48ebab0c12e03b54941b/84944c1def9ac6fe8cdcddc26dbd5fcdc7e1ec4701a8ccece74cbd6a2b688715",
                icon_key="booking-com"
            ),
            AffiliateLink(
                spot_id=test_spot.id,
                platform="rakuten",
                url="https://travel.rakuten.co.jp/hotel/japan/tokyo/test-cafe/?f_no=1234",
                title="楽天トラベル",
                description="楽天ポイントが貯まる・使える",
                logo_url="https://cdn.builder.io/api/v1/image/assets/b8fa2d7a435f48ebab0c12e03b54941b/532d34cb618a990f64da51d78f6168753a428877874b771849ef370903a1d740",
                icon_key="rakuten-travel"
            ),
            AffiliateLink(
                spot_id=test_spot.id,
                platform="jalan",
                url="https://www.jalan.net/yad123456/",
                title="じゃらん",
                description="最大10%ポイント還元",
                logo_url="",
                icon_key="jalan"
            ),
            AffiliateLink(
                spot_id=test_spot.id,
                platform="expedia",
                url="https://www.expedia.co.jp/Tokyo-Hotels-Test-Cafe.h12345.Hotel-Information",
                title="Expedia",
                description="柔軟なキャンセルポリシー",
                logo_url="",
                icon_key="expedia"
            )
        ]
        
        # SNS投稿を追加
        social_posts = [
            SocialPost(
                user_id=test_user.id,
                spot_id=test_spot.id,
                platform="instagram",
                post_url="https://www.instagram.com/p/abcdefg/",
                post_id="abcdefg",
                thumbnail_url="https://cdn.builder.io/api/v1/image/assets/b8fa2d7a435f48ebab0c12e03b54941b/c4b6eceea17bf421958ffab803902982674183dbd0877d7757c20a985ff83966",
                caption="Test Cafeでの素敵な時間 #testcafe #tokyo"
            ),
            SocialPost(
                user_id=test_user.id,
                spot_id=test_spot.id,
                platform="twitter",
                post_url="https://twitter.com/user/status/123456789",
                post_id="123456789",
                thumbnail_url="https://cdn.builder.io/api/v1/image/assets/b8fa2d7a435f48ebab0c12e03b54941b/6b633b68e920d2d541c15dfbc0f06ca6e1a326e984e57cf41fc1f7a9a6582368",
                caption="Test Cafeのコーヒーは最高！ #testcafe"
            )
        ]
        
        # データベースに追加
        for link in affiliate_links:
            db.session.add(link)
        
        for post in social_posts:
            db.session.add(post)
        
        db.session.commit()
        
        print("テストデータを作成しました。")
        print(f"- Google Maps URL: {test_spot.google_maps_url}")
        print(f"- アフィリエイトリンク: {len(affiliate_links)}件")
        print(f"- SNS投稿: {len(social_posts)}件")

if __name__ == "__main__":
    create_test_data() 