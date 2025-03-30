# APIルート用のパッケージ初期化ファイル
# このファイルは空でもよいが、Pythonパッケージとして認識されるために必要

from flask import Blueprint, jsonify, request
from flask_login import current_user
from app import db, csrf
from app.models.user import User

# URL API用のブループリント
url_api_bp = Blueprint('url_api', __name__, url_prefix='/api')

@url_api_bp.route('/check-display-name', methods=['GET'])
@csrf.exempt
def check_display_name():
    """表示名の利用可能性をチェックするAPI"""
    display_name = request.args.get('display_name', '')
    
    # 自分自身のdisplay_nameの場合は使用可能
    if current_user.is_authenticated and current_user.display_name == display_name:
        return jsonify({'available': True})
    
    is_valid, _ = User.validate_display_name(display_name)
    return jsonify({'available': is_valid}) 