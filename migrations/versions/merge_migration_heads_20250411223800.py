"""マイグレーションヘッドのマージ

Revision ID: merge_heads_20250411
Revises: add_rakuten_affiliate_id, add_summary_location_to_spots, 293a57f8c925
Create Date: 2025-04-11 22:38:00.084652

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_heads_20250411'
down_revision = ('add_rakuten_affiliate_id', 'add_summary_location_to_spots', '293a57f8c925')
branch_labels = None
depends_on = None


def upgrade():
    # 既存のテーブルと構造を維持
    pass


def downgrade():
    # 何も変更していないので何もしない
    pass
