from flask import Blueprint, render_template, abort
from app.models import User, Spot, Photo, SocialAccount
from sqlalchemy.orm import joinedload

public_bp = Blueprint('public', __name__)

@public_bp.route('/u/<int:user_id>')
def profile(user_id):
    """公開プロフィールページを表示する"""
    user = User.query.get_or_404(user_id)
    
    # 公開されているスポットのみを取得
    spots = Spot.query.filter_by(user_id=user_id, is_active=True).all()
    
    # ソーシャルアカウント情報を取得
    social_accounts = SocialAccount.query.filter_by(user_id=user_id).first()
    
    return render_template('public/profile.html', 
                          user=user, 
                          spots=spots, 
                          social_accounts=social_accounts)

@public_bp.route('/spot/<int:spot_id>')
def spot_detail(spot_id):
    """スポット詳細ページを表示する"""
    # スポットとそれに関連する写真を一度に取得
    spot = Spot.query.options(joinedload(Spot.user)).get_or_404(spot_id)
    
    # 非公開のスポットの場合は404を返す
    if not spot.is_active:
        abort(404)
    
    # スポットに関連する写真を取得
    photos = Photo.query.filter_by(spot_id=spot_id).all()
    
    return render_template('public/spot_detail.html', 
                          spot=spot, 
                          photos=photos) 