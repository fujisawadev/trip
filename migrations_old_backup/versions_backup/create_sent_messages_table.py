"""create sent_messages table

Revision ID: 293a57f8c925
Revises: add_missing_user_columns
Create Date: 2025-03-23 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text
import logging

# revision identifiers, used by Alembic.
revision = '293a57f8c925'
down_revision = 'add_missing_user_columns'
branch_labels = None
depends_on = None

logger = logging.getLogger('alembic.migration')

def table_exists(table_name):
    """テーブルが存在するかチェック"""
    bind = op.get_bind()
    conn = bind.connect()
    try:
        # PostgreSQLのinformation_schemaからテーブルの存在を確認
        result = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :table)"
            ),
            {"table": table_name}
        ).scalar()
        return result
    finally:
        conn.close()

def column_exists(table, column):
    """指定されたカラムがテーブルに存在するかチェック"""
    bind = op.get_bind()
    conn = bind.connect()
    try:
        # PostgreSQLのinformation_schemaからカラムの存在を確認
        result = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column)"
            ),
            {"table": table, "column": column}
        ).scalar()
        return result
    finally:
        conn.close()

def index_exists(index_name):
    """インデックスが存在するかチェック"""
    bind = op.get_bind()
    conn = bind.connect()
    try:
        # PostgreSQLのpg_indexesからインデックスの存在を確認
        result = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_indexes "
                "WHERE indexname = :index)"
            ),
            {"index": index_name}
        ).scalar()
        return result
    finally:
        conn.close()

def upgrade():
    # sent_messagesテーブルが既に存在するかチェック
    if not table_exists('sent_messages'):
        # sent_messagesテーブルの作成
        op.create_table('sent_messages',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('spot_id', sa.Integer(), nullable=False),
            sa.Column('message_type', sa.String(length=50), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('sent_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['spot_id'], ['spots.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        logger.info("Created sent_messages table")
    else:
        logger.info("sent_messages table already exists, skipping")
    
    # カラムが存在するかチェックしてからインデックス作成
    # スキーマチェック
    has_new_schema = (
        column_exists('sent_messages', 'user_id') and 
        column_exists('sent_messages', 'spot_id') and
        column_exists('sent_messages', 'message_type')
    )
    
    has_old_schema = (
        column_exists('sent_messages', 'sender_id') and
        column_exists('sent_messages', 'recipient_id') and
        column_exists('sent_messages', 'message_id')
    )
    
    if has_new_schema:
        # 新しいスキーマ用のインデックス（必要に応じて作成）
        if not index_exists('ix_sent_messages_user_id'):
            op.create_index(op.f('ix_sent_messages_user_id'), 'sent_messages', ['user_id'], unique=False)
            logger.info("Created index ix_sent_messages_user_id")
        
        if not index_exists('ix_sent_messages_spot_id'):
            op.create_index(op.f('ix_sent_messages_spot_id'), 'sent_messages', ['spot_id'], unique=False)
            logger.info("Created index ix_sent_messages_spot_id")
    
    elif has_old_schema:
        # 古いスキーマ用のインデックス（必要に応じて作成）
        if not index_exists('ix_sender_recipient'):
            op.create_index(op.f('ix_sender_recipient'), 'sent_messages', ['sender_id', 'recipient_id'], unique=False)
            logger.info("Created index ix_sender_recipient")
        
        if not index_exists('ix_sent_messages_message_id'):
            op.create_index(op.f('ix_sent_messages_message_id'), 'sent_messages', ['message_id'], unique=False)
            logger.info("Created index ix_sent_messages_message_id")
        
        if not index_exists('ix_sent_messages_sender_id'):
            op.create_index(op.f('ix_sent_messages_sender_id'), 'sent_messages', ['sender_id'], unique=False)
            logger.info("Created index ix_sent_messages_sender_id")
        
        if not index_exists('ix_sent_messages_recipient_id'):
            op.create_index(op.f('ix_sent_messages_recipient_id'), 'sent_messages', ['recipient_id'], unique=False)
            logger.info("Created index ix_sent_messages_recipient_id")
    else:
        logger.warning("Sent messages table structure is unknown, skipping index creation")


def downgrade():
    # スキーマチェック
    has_new_schema = (
        column_exists('sent_messages', 'user_id') and 
        column_exists('sent_messages', 'spot_id') and
        column_exists('sent_messages', 'message_type')
    )
    
    has_old_schema = (
        column_exists('sent_messages', 'sender_id') and
        column_exists('sent_messages', 'recipient_id') and
        column_exists('sent_messages', 'message_id')
    )
    
    # インデックスの削除（存在する場合のみ）
    if has_new_schema:
        # 新しいスキーマのインデックス
        if index_exists('ix_sent_messages_spot_id'):
            op.drop_index(op.f('ix_sent_messages_spot_id'), table_name='sent_messages')
        
        if index_exists('ix_sent_messages_user_id'):
            op.drop_index(op.f('ix_sent_messages_user_id'), table_name='sent_messages')
    
    elif has_old_schema:
        # 古いスキーマのインデックス
        if index_exists('ix_sent_messages_recipient_id'):
            op.drop_index(op.f('ix_sent_messages_recipient_id'), table_name='sent_messages')
        
        if index_exists('ix_sent_messages_sender_id'):
            op.drop_index(op.f('ix_sent_messages_sender_id'), table_name='sent_messages')
        
        if index_exists('ix_sent_messages_message_id'):
            op.drop_index(op.f('ix_sent_messages_message_id'), table_name='sent_messages')
        
        if index_exists('ix_sender_recipient'):
            op.drop_index(op.f('ix_sender_recipient'), table_name='sent_messages')
    
    # テーブルの削除（存在する場合のみ）
    if table_exists('sent_messages'):
        op.drop_table('sent_messages') 