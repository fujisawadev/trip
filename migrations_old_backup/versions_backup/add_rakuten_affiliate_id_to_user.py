"""add rakuten_affiliate_id to user model

Revision ID: add_rakuten_affiliate_id
Revises: 761e85bfa4d5
Create Date: 2025-04-11 22:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rakuten_affiliate_id'
down_revision = '761e85bfa4d5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('rakuten_affiliate_id', sa.String(length=100), nullable=True))


def downgrade():
    op.drop_column('users', 'rakuten_affiliate_id') 