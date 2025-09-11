"""add instagram token expiry columns to users

Revision ID: ef12ab34cd78
Revises: ed7a33d3f886
Create Date: 2025-09-10 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ef12ab34cd78'
down_revision = 'ed7a33d3f886'
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    try:
        cols = [c['name'] for c in inspector.get_columns(table_name)]
        return column_name in cols
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # instagram_token_expires_at
    if not _has_column(inspector, 'users', 'instagram_token_expires_at'):
        op.add_column('users', sa.Column('instagram_token_expires_at', sa.DateTime(timezone=True), nullable=True))

    # instagram_token_last_refreshed_at
    if not _has_column(inspector, 'users', 'instagram_token_last_refreshed_at'):
        op.add_column('users', sa.Column('instagram_token_last_refreshed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, 'users', 'instagram_token_last_refreshed_at'):
        op.drop_column('users', 'instagram_token_last_refreshed_at')

    if _has_column(inspector, 'users', 'instagram_token_expires_at'):
        op.drop_column('users', 'instagram_token_expires_at')


