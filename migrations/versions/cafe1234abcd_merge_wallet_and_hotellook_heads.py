"""merge heads: stripe/wallet branch and event_log bot flag

Revision ID: cafe1234abcd
Revises: 5d2a1c3b9e77, b1a2c3d4e5f6
Create Date: 2025-09-08 15:22:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cafe1234abcd'
down_revision = ('5d2a1c3b9e77', 'b1a2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass


