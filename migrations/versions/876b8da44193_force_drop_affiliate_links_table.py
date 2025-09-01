"""force drop affiliate_links table

Revision ID: 876b8da44193
Revises: ade41e323102
Create Date: 2025-08-29 18:36:04.669473

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '876b8da44193'
down_revision = 'ade41e323102'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if 'affiliate_links' in tables:
        # Use raw SQL to ensure CASCADE
        op.execute('DROP TABLE IF EXISTS affiliate_links CASCADE')


def downgrade():
    pass
