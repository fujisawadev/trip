"""update_nullable_constraints_for_postgresql

Revision ID: 1c9b714e4aca
Revises: 9e7aaf17f0f8
Create Date: 2025-03-04 19:36:38.802642

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1c9b714e4aca'
down_revision = '9e7aaf17f0f8'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('social_accounts', 'display_order',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('social_accounts', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('social_accounts', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('social_accounts', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('social_accounts', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('social_accounts', 'display_order',
               existing_type=sa.INTEGER(),
               nullable=True)
    # ### end Alembic commands ###
