# APIルート用のパッケージ初期化ファイル
# このファイルは空でもよいが、Pythonパッケージとして認識されるために必要

from flask import Blueprint, jsonify, request
from flask_login import current_user
from app import db, csrf
from app.models.user import User

# URL API用のブループリント
url_api_bp = Blueprint('url_api', __name__, url_prefix='/api')

@url_api_bp.route('/check-slug', methods=['GET'])
@csrf.exempt
def check_display_name():
    """slug の利用可能性をチェックするAPI"""
    slug = request.args.get('slug', '') or request.args.get('display_name', '')
    
    # 自分自身のdisplay_nameの場合は使用可能
    if current_user.is_authenticated and current_user.slug == slug:
        return jsonify({'available': True})
    
    is_valid, _ = User.validate_slug(slug)
    return jsonify({'available': is_valid}) 