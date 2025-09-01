"""add_save_job_fields_to_import_progress

Revision ID: 1f59993f4a2b
Revises: 17b3783dc5b5
Create Date: 2025-07-01 20:50:48.266246

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f59993f4a2b'
down_revision = '17b3783dc5b5'
branch_labels = None
depends_on = None


def upgrade():
    # ImportProgressテーブルに保存ジョブ用のカラムを追加（存在チェック付き）
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c['name'] for c in inspector.get_columns('import_progress')]

    if 'save_job_id' not in cols:
        op.add_column('import_progress', sa.Column('save_job_id', sa.String(36), nullable=True))
    if 'save_status' not in cols:
        op.add_column('import_progress', sa.Column('save_status', sa.String(20), nullable=True))
    if 'save_result_data' not in cols:
        op.add_column('import_progress', sa.Column('save_result_data', sa.Text(), nullable=True))
    if 'save_error_info' not in cols:
        op.add_column('import_progress', sa.Column('save_error_info', sa.Text(), nullable=True))


def downgrade():
    # カラムを削除
    try:
        op.drop_column('import_progress', 'save_error_info')
        op.drop_column('import_progress', 'save_result_data')
        op.drop_column('import_progress', 'save_status')
        op.drop_column('import_progress', 'save_job_id')
    except Exception:
        pass
