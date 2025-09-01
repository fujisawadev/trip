"""add spot_provider_ids table

Revision ID: 9c1a2f4b7cde
Revises: 3a8f1d2c9b7a
Create Date: 2025-08-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '9c1a2f4b7cde'
down_revision = '3a8f1d2c9b7a'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if 'spot_provider_ids' not in tables:
        op.create_table(
            'spot_provider_ids',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('spot_id', sa.Integer(), sa.ForeignKey('spots.id', ondelete='CASCADE'), nullable=False),
            sa.Column('provider', sa.String(length=50), nullable=False),
            sa.Column('external_id', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
            sa.Column('updated_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        )
    # 索引は存在チェックしてから作成
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('spot_provider_ids')] if 'spot_provider_ids' in tables else []
    if 'ix_spot_provider_ids_spot_provider' not in existing_indexes and 'spot_provider_ids' in tables:
        op.create_index('ix_spot_provider_ids_spot_provider', 'spot_provider_ids', ['spot_id', 'provider'], unique=True)


def downgrade():
    op.drop_index('ix_spot_provider_ids_spot_provider', table_name='spot_provider_ids')
    op.drop_table('spot_provider_ids')


