"""stamp to match staging

Revision ID: stamp_staging_sync
Revises: 224c661d1d75
Create Date: 2025-04-11 23:15:26.677437

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text
import logging

# revision identifiers, used by Alembic.
revision = 'stamp_staging_sync'
down_revision = '224c661d1d75'
branch_labels = None
depends_on = None

logger = logging.getLogger('alembic.migration')

def upgrade():
    """
    このマイグレーションはステージング環境との同期用のスタンプマイグレーションです。
    実際のデータベースの変更は行いませんが、マイグレーション履歴を
    ステージング環境と整合性を取るために使用します。
    
    ステージング環境のマイグレーションヘッド: 293a57f8c925
    ローカル環境のマイグレーションパス: merge_heads_20250411 -> 224c661d1d75 -> stamp_staging_sync
    """
    logger.info("ステージング環境との同期スタンプを適用しました")
    pass


def downgrade():
    pass
