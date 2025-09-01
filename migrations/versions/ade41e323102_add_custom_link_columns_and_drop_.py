"""add custom_link columns and drop affiliate_links

Revision ID: ade41e323102
Revises: 770054ec76a7
Create Date: 2025-08-29 18:33:30.992901

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ade41e323102'
down_revision = '770054ec76a7'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # spots: add custom_link_* if missing
    cols = [c['name'] for c in inspector.get_columns('spots')]
    if 'custom_link_title' not in cols:
        op.add_column('spots', sa.Column('custom_link_title', sa.Text(), nullable=True))
    if 'custom_link_url' not in cols:
        op.add_column('spots', sa.Column('custom_link_url', sa.Text(), nullable=True))

    # drop affiliate_links if exists
    tables = inspector.get_table_names()
    if 'affiliate_links' in tables:
        op.drop_table('affiliate_links')


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # recreate affiliate_links (minimal) if not exists
    tables = inspector.get_table_names()
    if 'affiliate_links' not in tables:
        op.create_table(
            'affiliate_links',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('spot_id', sa.Integer(), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('url', sa.Text(), nullable=False),
            sa.Column('title', sa.Text(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('logo_url', sa.Text(), nullable=True),
            sa.Column('icon_key', sa.String(length=50), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )

    # drop custom_link_* if exists
    cols = [c['name'] for c in inspector.get_columns('spots')]
    if 'custom_link_title' in cols:
        op.drop_column('spots', 'custom_link_title')
    if 'custom_link_url' in cols:
        op.drop_column('spots', 'custom_link_url')
