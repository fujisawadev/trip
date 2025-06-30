"""clean_up_users_table

Revision ID: 68928dcafc4f
Revises: stamp_staging_sync
Create Date: 2025-04-11 23:31:31.368978

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text
import logging

# revision identifiers, used by Alembic.
revision = '68928dcafc4f'
down_revision = 'stamp_staging_sync'
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
    except Exception as e:
        logger.warning(f"カラム存在チェックでエラーが発生: {e}")
        return False
    finally:
        conn.close()

def upgrade():
    """
    usersテーブルから不要なカラムを削除します。
    
    1. 重複しているカラム: reset_token, reset_token_expires_at, profile_image
    2. 未使用のカラム: settings, preferences, is_admin, is_active, website, location
    
    また、データ型の変更とユニーク制約も調整します。
    """
    conn = op.get_bind()
    
    # 安全にカラム削除を行うためのトランザクション
    try:
        # ユーザーの不要なカラムを削除
        logger.info("usersテーブルから不要なカラムを削除します")
        
        # 重複しているリセットトークン関連カラムを削除
        if column_exists('users', 'reset_token'):
            op.drop_column('users', 'reset_token')
            logger.info("reset_tokenカラムを削除しました")
            
        if column_exists('users', 'reset_token_expires_at'):
            op.drop_column('users', 'reset_token_expires_at')
            logger.info("reset_token_expires_atカラムを削除しました")
        
        # 未使用のプロフィール画像カラムを削除
        if column_exists('users', 'profile_image'):
            op.drop_column('users', 'profile_image')
            logger.info("profile_imageカラムを削除しました")
            
        # 未使用のJSON設定カラムを削除
        if column_exists('users', 'settings'):
            op.drop_column('users', 'settings')
            logger.info("settingsカラムを削除しました")
            
        if column_exists('users', 'preferences'):
            op.drop_column('users', 'preferences')
            logger.info("preferencesカラムを削除しました")
            
        # 未使用のユーザー状態カラムを削除
        if column_exists('users', 'is_admin'):
            op.drop_column('users', 'is_admin')
            logger.info("is_adminカラムを削除しました")
            
        if column_exists('users', 'is_active'):
            op.drop_column('users', 'is_active')
            logger.info("is_activeカラムを削除しました")
            
        # 未使用のウェブサイトとロケーションカラムを削除
        if column_exists('users', 'website'):
            op.drop_column('users', 'website')
            logger.info("websiteカラムを削除しました")
            
        if column_exists('users', 'location'):
            op.drop_column('users', 'location')
            logger.info("locationカラムを削除しました")
            
        # データ型調整とインデックス再構築
        try:
            op.alter_column('users', 'username',
                       existing_type=sa.VARCHAR(length=64),
                       type_=sa.String(length=80),
                       existing_nullable=False)
                       
            op.alter_column('users', 'bio',
                       existing_type=sa.TEXT(),
                       type_=sa.String(length=500),
                       existing_nullable=True)
                       
            op.alter_column('users', 'profile_pic_url',
                       existing_type=sa.VARCHAR(length=255),
                       type_=sa.String(length=500),
                       existing_nullable=True)
                       
            # インデックスの再構築（存在する場合のみ削除）
            if conn.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_users_email'")).scalar():
                op.drop_index('ix_users_email', table_name='users')
                
            if conn.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_users_username'")).scalar():
                op.drop_index('ix_users_username', table_name='users')
                
            # ユニーク制約を追加
            op.create_unique_constraint('uq_users_email', 'users', ['email'])
            op.create_unique_constraint('uq_users_display_name', 'users', ['display_name'])
            op.create_unique_constraint('uq_users_username', 'users', ['username'])
            
            logger.info("usersテーブルのデータ型とインデックスを調整しました")
        except Exception as e:
            logger.warning(f"データ型またはインデックス調整中にエラーが発生: {e}")
            
    except Exception as e:
        logger.error(f"カラム削除中にエラーが発生: {e}")
        raise

def downgrade():
    """
    削除したカラムを元に戻します。
    """
    try:
        # 削除したカラムを追加
        op.add_column('users', sa.Column('profile_image', sa.VARCHAR(length=200), autoincrement=False, nullable=True))
        op.add_column('users', sa.Column('is_active', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False))
        op.add_column('users', sa.Column('reset_token', sa.VARCHAR(length=100), autoincrement=False, nullable=True))
        op.add_column('users', sa.Column('is_admin', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
        op.add_column('users', sa.Column('preferences', postgresql.JSON(astext_type=sa.Text()), server_default=sa.text("'{}'::json"), autoincrement=False, nullable=True))
        op.add_column('users', sa.Column('reset_token_expires_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        op.add_column('users', sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), server_default=sa.text("'{}'::json"), autoincrement=False, nullable=True))
        op.add_column('users', sa.Column('website', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
        op.add_column('users', sa.Column('location', sa.VARCHAR(length=100), autoincrement=False, nullable=True))
        
        # 制約の調整
        op.drop_constraint('uq_users_username', 'users', type_='unique')
        op.drop_constraint('uq_users_display_name', 'users', type_='unique')
        op.drop_constraint('uq_users_email', 'users', type_='unique')
        
        # インデックスの再作成
        op.create_index('ix_users_username', 'users', ['username'], unique=True)
        op.create_index('ix_users_email', 'users', ['email'], unique=True)
        
        # データ型を元に戻す
        op.alter_column('users', 'profile_pic_url',
                   existing_type=sa.String(length=500),
                   type_=sa.VARCHAR(length=255),
                   existing_nullable=True)
        op.alter_column('users', 'bio',
                   existing_type=sa.String(length=500),
                   type_=sa.TEXT(),
                   existing_nullable=True)
        op.alter_column('users', 'username',
                   existing_type=sa.String(length=80),
                   type_=sa.VARCHAR(length=64),
                   existing_nullable=False)
        
        logger.info("usersテーブルを元の状態に戻しました")
    except Exception as e:
        logger.error(f"ダウングレード中にエラーが発生: {e}")
        raise
