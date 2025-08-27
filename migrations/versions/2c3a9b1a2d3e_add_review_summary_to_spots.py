"""add review_summary to spots

Revision ID: 2c3a9b1a2d3e
Revises: 1f59993f4a2b
Create Date: 2025-08-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c3a9b1a2d3e'
down_revision = '1f59993f4a2b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('spots', sa.Column('review_summary', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('spots', 'review_summary')



