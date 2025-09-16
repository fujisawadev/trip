"""
新しいエージェントAPI

Step 0 & Step 1の機能を提供する統合エージェントAPIです。
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm import joinedload
from flask_wtf import CSRFProtect

from app.services.agents.manager_v3 import AgentManagerV3
from app.models.spot import Spot
from app.models.user import User
from app.models.photo import Photo
from app import db

logger = logging.getLogger(__name__)

# Blueprint作成 (V3)
agents_v3_bp = Blueprint('agents_v3', __name__)

# グローバルエージェントマネージャー（本来はDIコンテナで管理すべき）
agent_manager_v3 = AgentManagerV3()

@agents_v3_bp.route('/chat', methods=['POST'])
def chat_v3():
    """新しいエージェント(V3)のチャット処理"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'リクエストデータが不正です'
            }), 400
        
        message = data.get('message', '').strip()
        context_type = data.get('context_type', 'general')
        influencer_id = data.get('influencer_id')
        spot_id = data.get('spot_id')
        session_id = data.get('session_id', 'default_session')
        
        if not message:
            return jsonify({
                'success': False,
                'error': 'メッセージが空です'
            }), 400
        
        # コンテキスト構築 (既存のものを流用)
        context = _build_context(context_type, influencer_id, spot_id)
        
        if not context['success']:
            return jsonify({
                'success': False,
                'error': context['error']
            }), 400

        # V3エージェントマネージャーを呼び出す
        result = agent_manager_v3.handle_message(
            message=message,
            context=context['data'],
            session_id=session_id
        )
        
        return jsonify(result)

    except Exception as e:
        logger.error(f"Chat v3 endpoint error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'V3エージェントでシステムエラーが発生しました'
        }), 500

@agents_v3_bp.route('/quick-prompts', methods=['POST'])
def get_quick_prompts_v3():
    """V3: クイックプロンプト取得エンドポイント"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'リクエストデータが不正です'
            }), 400
        
        context_type = data.get('context_type', 'general')
        influencer_id = data.get('influencer_id')
        spot_id = data.get('spot_id')
        
        # 共通のコンテキスト構築関数を使用
        context = _build_context(context_type, influencer_id, spot_id)
        
        if not context['success']:
            return jsonify({
                'success': False,
                'error': context['error']
            }), 400
        
        # V3マネージャーのプロンプト生成機能を呼び出す
        prompts = agent_manager_v3.generate_quick_prompts(context['data'])
        
        return jsonify({
            'success': True,
            'prompts': prompts
        })
        
    except Exception as e:
        logger.error(f"Quick prompts v3 endpoint error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'システムエラーが発生しました'
        }), 500

def _build_context(context_type: str, influencer_id: int = None, spot_id: int = None) -> dict:
    """APIリクエスト用のコンテキストを構築"""
    try:
        context = {
            'page_type': context_type,
            'timestamp': datetime.now().isoformat()
        }
        
        if context_type == 'profile' and influencer_id:
            # プロフィールページのコンテキスト
            influencer = User.query.get(influencer_id)
            if not influencer:
                return {'success': False, 'error': 'インフルエンサーが見つかりません'}
            
            context['influencer_info'] = _serialize_user(influencer)
            
            # 公開スポット一覧をユーザー情報とともに取得
            spots = Spot.query.options(
                joinedload(Spot.user)
            ).filter_by(
                user_id=influencer_id,
                is_active=True
            ).all()
            
            context['spots'] = [_serialize_spot(s) for s in spots]
            
            return {'success': True, 'data': context}
        
        elif context_type == 'spot_detail' and spot_id:
            # スポット詳細ページのコンテキスト
            spot = Spot.query.options(
                joinedload(Spot.user)
            ).get(spot_id)
            
            if not spot or not spot.is_active:
                return {'success': False, 'error': 'スポットが見つからないか、非公開です'}
            
            context['spot_info'] = _serialize_spot(spot)
            
            return {'success': True, 'data': context}
        
        # コンテキストが不要な場合は空のデータを返す
        return {'success': True, 'data': context}
        
    except Exception as e:
        logger.error(f"Context building error: {e}", exc_info=True)
        return {'success': False, 'error': 'コンテキストの構築中にエラーが発生しました'}

def _serialize_user(user: User) -> dict:
    """ユーザーモデルを辞書に変換"""
    return {
        'id': user.id,
        'username': user.username,
        'slug': user.slug,
        'bio': user.bio,
        'profile_pic_url': user.profile_pic_url
    }

def _serialize_spot(spot: Spot) -> dict:
    """スポットモデルを辞書に変換（URL生成に必要な情報を含む）"""
    return {
        'id': spot.id,
        'name': spot.name,
        'description': spot.description,
        'category': spot.category,
        'created_at': spot.created_at.isoformat() if spot.created_at else None,
        'rating': float(spot.rating) if spot.rating else None,
        'formatted_address': spot.formatted_address,
        'summary_location': spot.summary_location,
        # URL生成のためにユーザー情報を含める
        'user': {
            'id': spot.user.id,
            'username': spot.user.username,
            'slug': spot.user.slug
        }
    } 