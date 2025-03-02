from app.models import Spot; spots = Spot.query.all(); [print(f"ID: {s.id}, Name: {s.name}, Google Place ID: {s.google_place_id}, Photos: {len(s.photos)}") for s in spots]
