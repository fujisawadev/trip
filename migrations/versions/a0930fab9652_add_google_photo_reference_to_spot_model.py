"""Add google_photo_reference to Spot model

Revision ID: a0930fab9652
Revises: 761e85bfa4d5
Create Date: 2025-03-02 14:13:11.409369

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a0930fab9652'
down_revision = '761e85bfa4d5'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('spots', sa.Column('google_photo_reference', sa.String(length=255), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('spots', 'google_photo_reference')
    # ### end Alembic commands ###
