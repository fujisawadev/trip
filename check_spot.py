from app import create_app, db
from app.models import Spot

app = create_app()
with app.app_context():
    spot = Spot.query.get(5)
    if spot:
        print(f'ID: {spot.id}')
        print(f'Name: {spot.name}')
        print(f'Google Place ID: {spot.google_place_id}')
        print(f'Google Photo Reference: {spot.google_photo_reference}')
    else:
        print('Spot with ID 5 not found')
