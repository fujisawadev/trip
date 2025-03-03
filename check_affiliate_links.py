import sys
sys.path.append('/Users/air/Develop/trip')
from app import create_app
app = create_app()
with app.app_context():
    from app.models import AffiliateLink
    links = AffiliateLink.query.filter_by(spot_id=1).all()
    print('Found links:', len(links))
    for link in links:
        print(f'- ID:{link.id}, Platform:{link.platform}, Active:{link.is_active}, Title:{link.title}') 