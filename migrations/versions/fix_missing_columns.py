"""fix missing columns in Heroku environment

Revision ID: fix_missing_columns
Revises: dbd812da48ab
Create Date: 2025-03-18 11:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_missing_columns'
down_revision = 'dbd812da48ab'
branch_labels = None
depends_on = None


def upgrade():
    # Try to add missing columns, ignore if they already exist
    try:
        op.add_column('photos', sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'))
    except Exception as e:
        print(f"Could not add is_primary column to photos: {e}")
    
    try:
        op.add_column('users', sa.Column('last_login', sa.DateTime(), nullable=True))
    except Exception as e:
        print(f"Could not add last_login column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('instagram_business_id', sa.String(length=64), nullable=True))
    except Exception as e:
        print(f"Could not add instagram_business_id column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('website', sa.String(length=255), nullable=True))
    except Exception as e:
        print(f"Could not add website column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('location', sa.String(length=100), nullable=True))
    except Exception as e:
        print(f"Could not add location column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('autoreply_enabled', sa.Boolean(), nullable=True, server_default='false'))
    except Exception as e:
        print(f"Could not add autoreply_enabled column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('autoreply_template', sa.Text(), nullable=True))
    except Exception as e:
        print(f"Could not add autoreply_template column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('autoreply_last_updated', sa.DateTime(), nullable=True))
    except Exception as e:
        print(f"Could not add autoreply_last_updated column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=True, server_default='false'))
    except Exception as e:
        print(f"Could not add is_verified column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('verification_token', sa.String(length=64), nullable=True))
    except Exception as e:
        print(f"Could not add verification_token column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('verification_sent_at', sa.DateTime(), nullable=True))
    except Exception as e:
        print(f"Could not add verification_sent_at column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('reset_password_token', sa.String(length=100), nullable=True))
    except Exception as e:
        print(f"Could not add reset_password_token column to users: {e}")
    
    try:
        op.add_column('users', sa.Column('reset_password_expires', sa.DateTime(), nullable=True))
    except Exception as e:
        print(f"Could not add reset_password_expires column to users: {e}")


def downgrade():
    # No downgrade needed for this fix
    pass 