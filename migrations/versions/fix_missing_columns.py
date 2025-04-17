"""fix missing columns in Heroku environment

Revision ID: fix_missing_columns
Revises: dbd812da48ab
Create Date: 2025-03-18 11:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text
import logging

# revision identifiers, used by Alembic.
revision = 'fix_missing_columns'
down_revision = 'dbd812da48ab'
branch_labels = None
depends_on = None

logger = logging.getLogger('alembic.migration')

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

def add_column_if_not_exists(table, column, column_def):
    """カラムが存在しない場合のみ追加"""
    if not column_exists(table, column):
        try:
            op.add_column(table, column_def)
            logger.info(f"Added column {column} to {table}")
            return True
        except Exception as e:
            logger.error(f"Failed to add column {column} to {table}: {e}")
            return False
    else:
        logger.info(f"Column {column} already exists in {table}, skipping")
        return True

def upgrade():
    # 各カラムを追加（存在しない場合のみ）
    # photos テーブル
    add_column_if_not_exists('photos', 'is_primary', 
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'))
    
    # users テーブル - 基本情報
    add_column_if_not_exists('users', 'last_login', 
        sa.Column('last_login', sa.DateTime(), nullable=True))
    
    # users テーブル - Instagram 統合
    add_column_if_not_exists('users', 'instagram_business_id', 
        sa.Column('instagram_business_id', sa.String(length=64), nullable=True))
    add_column_if_not_exists('users', 'website', 
        sa.Column('website', sa.String(length=255), nullable=True))
    add_column_if_not_exists('users', 'location', 
        sa.Column('location', sa.String(length=100), nullable=True))
    
    # users テーブル - 自動応答機能
    add_column_if_not_exists('users', 'autoreply_enabled', 
        sa.Column('autoreply_enabled', sa.Boolean(), nullable=True, server_default='false'))
    add_column_if_not_exists('users', 'autoreply_template', 
        sa.Column('autoreply_template', sa.Text(), nullable=True))
    add_column_if_not_exists('users', 'autoreply_last_updated', 
        sa.Column('autoreply_last_updated', sa.DateTime(), nullable=True))
    
    # users テーブル - アカウント検証
    add_column_if_not_exists('users', 'is_verified', 
        sa.Column('is_verified', sa.Boolean(), nullable=True, server_default='false'))
    add_column_if_not_exists('users', 'verification_token', 
        sa.Column('verification_token', sa.String(length=64), nullable=True))
    add_column_if_not_exists('users', 'verification_sent_at', 
        sa.Column('verification_sent_at', sa.DateTime(), nullable=True))
    
    # users テーブル - パスワードリセット
    add_column_if_not_exists('users', 'reset_password_token', 
        sa.Column('reset_password_token', sa.String(length=100), nullable=True))
    add_column_if_not_exists('users', 'reset_password_expires', 
        sa.Column('reset_password_expires', sa.DateTime(), nullable=True))


def downgrade():
    # カラムを削除する処理は実装しない
    # この修正はカラムがない場合に追加するだけなので、
    # ダウングレードでは何もしない
    pass 