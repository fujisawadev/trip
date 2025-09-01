"""add review summary to spots

Revision ID: 2c3a9b1a2d3e
Revises: 17b3783dc5b5
Create Date: 2025-08-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c3a9b1a2d3e'
down_revision = '17b3783dc5b5'
branch_labels = None
depends_on = None


def upgrade():
    # 既存: review_summary 追加
    try:
        op.add_column('spots', sa.Column('review_summary', sa.Text(), nullable=True))
    except Exception:
        pass

    # 新規: custom_link_* が無ければ追加
    try:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        cols = [c['name'] for c in inspector.get_columns('spots')]
        if 'custom_link_title' not in cols:
            op.add_column('spots', sa.Column('custom_link_title', sa.Text(), nullable=True))
        if 'custom_link_url' not in cols:
            op.add_column('spots', sa.Column('custom_link_url', sa.Text(), nullable=True))
    except Exception:
        pass


def downgrade():
    # review_summary を削除
    try:
        op.drop_column('spots', 'review_summary')
    except Exception:
        pass

    # custom_link_* を削除（存在すれば）
    try:
        op.drop_column('spots', 'custom_link_title')
        op.drop_column('spots', 'custom_link_url')
    except Exception:
        pass



