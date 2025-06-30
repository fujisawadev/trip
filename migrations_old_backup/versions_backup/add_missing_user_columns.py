"""add missing user columns

Revision ID: add_missing_user_columns
Revises: fix_missing_columns
Create Date: 2025-03-21 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_missing_user_columns'
down_revision = 'add_facebook_integration_fields'
branch_labels = None
depends_on = None


def upgrade():
    # 不足しているカラムを追加（存在する場合はエラーを無視）
    try:
        op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    except Exception as e:
        print(f"Could not add is_active column: {e}")

    try:
        op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))
    except Exception as e:
        print(f"Could not add is_admin column: {e}")

    try:
        op.add_column('users', sa.Column('display_name', sa.String(length=100), nullable=True))
    except Exception as e:
        print(f"Could not add display_name column: {e}")

    try:
        op.add_column('users', sa.Column('profile_image', sa.String(length=200), nullable=True))
    except Exception as e:
        print(f"Could not add profile_image column: {e}")

    try:
        op.add_column('users', sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'))
    except Exception as e:
        print(f"Could not add settings column: {e}")

    try:
        op.add_column('users', sa.Column('preferences', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'))
    except Exception as e:
        print(f"Could not add preferences column: {e}")


def downgrade():
    # The columns will be kept in a downgrade scenario
    pass 