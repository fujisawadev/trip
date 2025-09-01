"""add hotel fields to spots

Revision ID: 3a8f1d2c9b7a
Revises: 2c3a9b1a2d3e
Create Date: 2025-08-22 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a8f1d2c9b7a'
down_revision = '2c3a9b1a2d3e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('spots', sa.Column('hotel_provider', sa.String(length=50), nullable=True))
    op.add_column('spots', sa.Column('hotel_provider_id', sa.String(length=100), nullable=True))
    op.create_index('ix_spots_hotel_provider_id', 'spots', ['hotel_provider', 'hotel_provider_id'], unique=False)


def downgrade():
    op.drop_index('ix_spots_hotel_provider_id', table_name='spots')
    op.drop_column('spots', 'hotel_provider_id')
    op.drop_column('spots', 'hotel_provider')




