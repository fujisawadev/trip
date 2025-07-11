"""Check for differences between DB and models

Revision ID: 3a11a6a1fc11
Revises: 4f4568c19a1a
Create Date: 2025-06-30 20:41:34.419306

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3a11a6a1fc11'
down_revision = '4f4568c19a1a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('social_posts', 'post_url',
               existing_type=sa.TEXT(),
               type_=sa.String(length=2048),
               existing_nullable=False)
    op.drop_column('social_posts', 'thumbnail_url')
    op.drop_column('social_posts', 'post_id')
    op.drop_column('social_posts', 'caption')
    op.alter_column('spots', 'rating',
               existing_type=postgresql.DOUBLE_PRECISION(precision=53),
               nullable=False,
               existing_server_default=sa.text("'0'::double precision"))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('spots', 'rating',
               existing_type=postgresql.DOUBLE_PRECISION(precision=53),
               nullable=True,
               existing_server_default=sa.text("'0'::double precision"))
    op.add_column('social_posts', sa.Column('caption', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('social_posts', sa.Column('post_id', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('social_posts', sa.Column('thumbnail_url', sa.TEXT(), autoincrement=False, nullable=True))
    op.alter_column('social_posts', 'post_url',
               existing_type=sa.String(length=2048),
               type_=sa.TEXT(),
               existing_nullable=False)
    # ### end Alembic commands ###
