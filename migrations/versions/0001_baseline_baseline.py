"""baseline

Revision ID: 0001_baseline
Revises: 
Create Date: 2025-06-30 21:25:02.746399

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create import_progress table with basic structure (10 columns)
    op.create_table('import_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=50), server_default='instagram', nullable=False),
        sa.Column('last_imported_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('last_post_id', sa.String(length=255), nullable=True),
        sa.Column('last_post_timestamp', sa.DateTime(), nullable=True),
        sa.Column('next_page_cursor', sa.String(length=255), nullable=True),
        sa.Column('total_imported_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('import_period_start', sa.DateTime(), nullable=True),
        sa.Column('import_period_end', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source', name='uix_import_progress_user_source')
    )


def downgrade():
    # Drop import_progress table
    op.drop_table('import_progress')
