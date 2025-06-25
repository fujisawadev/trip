from flask import Blueprint, render_template, redirect, url_for

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """トップページ"""
    return render_template('public/landing.html')

@bp.route('/debug-sentry')
def trigger_error():
    """Sentryのテスト用エラーを発生させる"""
    division_by_zero = 1 / 0
    return "This will never be reached."

@bp.errorhandler(404)
def page_not_found(e):
    """404エラーページ"""
    return render_template('404.html'), 404

@bp.errorhandler(500)
def internal_server_error(e):
    """500エラーページ"""
    return render_template('500.html'), 500 