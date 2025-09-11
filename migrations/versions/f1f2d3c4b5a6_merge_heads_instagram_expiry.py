"""merge heads after adding instagram expiry columns

Revision ID: f1f2d3c4b5a6
Revises: cafe1234abcd, ef12ab34cd78
Create Date: 2025-09-10 13:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1f2d3c4b5a6'
down_revision = ('cafe1234abcd', 'ef12ab34cd78')
branch_labels = None
depends_on = None


def upgrade():
    # merge migration: no-op
    pass


def downgrade():
    # merge migration: no-op
    pass


