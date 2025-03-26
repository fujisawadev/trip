"""create sent_messages table

Revision ID: 293a57f8c925
Revises: add_missing_user_columns
Create Date: 2025-03-23 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '293a57f8c925'
down_revision = 'add_missing_user_columns'
branch_labels = None
depends_on = None


def upgrade():
    # sent_messagesテーブルの作成
    op.create_table('sent_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.String(length=255), nullable=False),
        sa.Column('sender_id', sa.String(length=255), nullable=False),
        sa.Column('recipient_id', sa.String(length=255), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # インデックスの作成
    op.create_index(op.f('ix_sender_recipient'), 'sent_messages', ['sender_id', 'recipient_id'], unique=False)
    op.create_index(op.f('ix_sent_messages_message_id'), 'sent_messages', ['message_id'], unique=False)
    op.create_index(op.f('ix_sent_messages_sender_id'), 'sent_messages', ['sender_id'], unique=False)
    op.create_index(op.f('ix_sent_messages_recipient_id'), 'sent_messages', ['recipient_id'], unique=False)


def downgrade():
    # インデックスの削除
    op.drop_index(op.f('ix_sent_messages_recipient_id'), table_name='sent_messages')
    op.drop_index(op.f('ix_sent_messages_sender_id'), table_name='sent_messages')
    op.drop_index(op.f('ix_sent_messages_message_id'), table_name='sent_messages')
    op.drop_index(op.f('ix_sender_recipient'), table_name='sent_messages')
    
    # テーブルの削除
    op.drop_table('sent_messages') 