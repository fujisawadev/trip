from flask import Blueprint, jsonify, request, abort
from app.models import Spot, Photo
from sqlalchemy.orm import joinedload

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/spots/<int:spot_id>', methods=['GET'])
def get_spot(spot_id):
    """スポット詳細情報を取得するAPI"""
    # スポットとそれに関連する写真を一度に取得
    spot = Spot.query.options(joinedload(Spot.photos)).get_or_404(spot_id)
    
    # 非公開のスポットの場合は404を返す
    if not spot.is_active:
        abort(404)
    
    # スポットデータをJSON形式で返す
    spot_data = {
        'id': spot.id,
        'name': spot.name,
        'description': spot.description,
        'location': spot.location,
        'category': spot.category,
        'latitude': spot.latitude,
        'longitude': spot.longitude,
        'photos': [
            {
                'id': photo.id,
                'photo_url': photo.image_path
            } for photo in spot.photos
        ]
    }
    
    return jsonify(spot_data) 