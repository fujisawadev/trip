from flask import Blueprint, render_template

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """トップページ"""
    return render_template('public/new_lp.html')

@bp.errorhandler(404)
def page_not_found(e):
    """404エラーページ"""
    return render_template('public/404.html'), 404

@bp.errorhandler(500)
def internal_server_error(e):
    """500エラーページ"""
    return render_template('public/500.html'), 500 