"""Add last_login column to users table

Revision ID: dbd812da48ab
Revises: 6e4a0fa228db
Create Date: 2025-03-18 16:05:36.568519

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'dbd812da48ab'
down_revision = '6e4a0fa228db'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('last_login', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('verification_token', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('verification_sent_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('reset_password_token', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('reset_password_expires', sa.DateTime(), nullable=True))
    op.alter_column('users', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.drop_column('users', 'reset_token')
    op.drop_column('users', 'reset_token_expires_at')
    op.drop_column('users', 'updated_at')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False))
    op.add_column('users', sa.Column('reset_token_expires_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('reset_token', sa.VARCHAR(length=100), autoincrement=False, nullable=True))
    op.alter_column('users', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.drop_column('users', 'reset_password_expires')
    op.drop_column('users', 'reset_password_token')
    op.drop_column('users', 'verification_sent_at')
    op.drop_column('users', 'verification_token')
    op.drop_column('users', 'is_verified')
    op.drop_column('users', 'last_login')
    # ### end Alembic commands ###
