"""Add Google photo reference fields to Photo model

Revision ID: 761e85bfa4d5
Revises: 13dcb60c2176
Create Date: 2025-03-02 13:29:57.752894

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.sql import text
import logging

# revision identifiers, used by Alembic.
revision = '761e85bfa4d5'
down_revision = '15846cf6d16e'
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

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    # カラムが存在しない場合のみ追加
    if not column_exists('photos', 'google_photo_reference'):
        op.add_column('photos', sa.Column('google_photo_reference', sa.String(length=255), nullable=True))
        logger.info("Added google_photo_reference column to photos table")
    else:
        logger.info("google_photo_reference column already exists in photos table, skipping")
        
    if not column_exists('photos', 'is_google_photo'):
        op.add_column('photos', sa.Column('is_google_photo', sa.Boolean(), nullable=True))
        logger.info("Added is_google_photo column to photos table")
    else:
        logger.info("is_google_photo column already exists in photos table, skipping")
    
    # 既存の行のphoto_urlのnullableを処理
    conn = op.get_bind()
    conn.execute(text('UPDATE photos SET photo_url = photo_url'))
    
    # 緯度経度の型変更
    op.alter_column('spots', 'latitude',
               existing_type=sa.REAL(),
               type_=sa.Float(),
               existing_nullable=True)
    op.alter_column('spots', 'longitude',
               existing_type=sa.REAL(),
               type_=sa.Float(),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('spots', 'longitude',
               existing_type=sa.Float(),
               type_=sa.REAL(),
               existing_nullable=True)
    op.alter_column('spots', 'latitude',
               existing_type=sa.Float(),
               type_=sa.REAL(),
               existing_nullable=True)
    
    # ダウングレード時にphoto_urlがNULLの場合に空文字列を設定
    conn = op.get_bind()
    conn.execute(text('UPDATE photos SET photo_url = \'\' WHERE photo_url IS NULL'))
    
    # カラムが存在する場合のみ削除
    if column_exists('photos', 'is_google_photo'):
        op.drop_column('photos', 'is_google_photo')
        logger.info("Dropped is_google_photo column from photos table")
    else:
        logger.info("is_google_photo column doesn't exist in photos table, skipping")
        
    if column_exists('photos', 'google_photo_reference'):
        op.drop_column('photos', 'google_photo_reference')
        logger.info("Dropped google_photo_reference column from photos table")
    else:
        logger.info("google_photo_reference column doesn't exist in photos table, skipping")
    # ### end Alembic commands ###
