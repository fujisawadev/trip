"""drop hotellook columns from spots

Revision ID: aaaaaaaaaaaa
Revises: 9c1a2f4b7cde
Create Date: 2025-08-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = 'aaaaaaaaaaaa'
down_revision = '9c1a2f4b7cde'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c['name'] for c in inspector.get_columns('spots')]
    if 'hotel_provider' in cols:
        op.drop_column('spots', 'hotel_provider')
    if 'hotel_provider_id' in cols:
        op.drop_column('spots', 'hotel_provider_id')
    idx = [i['name'] for i in inspector.get_indexes('spots')]
    if 'ix_spots_hotel_provider_id' in idx:
        op.drop_index('ix_spots_hotel_provider_id', table_name='spots')

    # 追加: affiliate_links テーブルを削除（存在する場合）
    tables = inspector.get_table_names()
    if 'affiliate_links' in tables:
        op.drop_table('affiliate_links')


def downgrade():
    op.add_column('spots', sa.Column('hotel_provider', sa.String(length=50), nullable=True))
    op.add_column('spots', sa.Column('hotel_provider_id', sa.String(length=100), nullable=True))
    op.create_index('ix_spots_hotel_provider_id', 'spots', ['hotel_provider', 'hotel_provider_id'], unique=False)


