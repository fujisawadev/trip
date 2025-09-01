"""add is_bot and bot_reason to event_log

Revision ID: b1a2c3d4e5f6
Revises: ed7a33d3f886
Create Date: 2025-09-01 07:26:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1a2c3d4e5f6'
down_revision = 'ed7a33d3f886'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = []
    try:
        cols = [c['name'] for c in inspector.get_columns('event_log')]
    except Exception:
        cols = []

    if 'is_bot' not in cols:
        op.add_column('event_log', sa.Column('is_bot', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    if 'bot_reason' not in cols:
        op.add_column('event_log', sa.Column('bot_reason', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = []
    try:
        cols = [c['name'] for c in inspector.get_columns('event_log')]
    except Exception:
        cols = []
    if 'bot_reason' in cols:
        op.drop_column('event_log', 'bot_reason')
    if 'is_bot' in cols:
        op.drop_column('event_log', 'is_bot')


