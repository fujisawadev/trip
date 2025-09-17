from alembic import op
import sqlalchemy as sa

revision = 'ef56_eventlog_ondelete_setnull'
down_revision = 'ef34abcd1234'
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL: 既存FKを落として ON DELETE SET NULL で作り直し、page_id を NULL 許容に変更
    conn = op.get_bind()

    # 1) NULL許容へ
    op.alter_column('event_log', 'page_id', existing_type=sa.BigInteger(), nullable=True)

    # 2) 既存の外部キー制約名を推定/取得して削除（名称が固定でない場合に備えSQL実行）
    # 可能なら固定名に置き換えてください
    try:
        op.drop_constraint('event_log_page_id_fkey', 'event_log', type_='foreignkey')
    except Exception:
        # フォールバック: 一致するFKを探して削除
        res = conn.execute(sa.text("""
            SELECT conname FROM pg_constraint c
            JOIN pg_class r ON r.oid = c.conrelid
            WHERE r.relname = 'event_log' AND conname LIKE '%page_id%fkey%'
        """)).fetchall()
        for row in res:
            try:
                op.drop_constraint(row[0], 'event_log', type_='foreignkey')
            except Exception:
                pass

    # 3) 新しいFKを ON DELETE SET NULL で作成
    op.create_foreign_key(
        'event_log_page_id_fkey',
        'event_log', 'spots',
        ['page_id'], ['id'], ondelete='SET NULL'
    )


def downgrade():
    # 元に戻す（NULL非許容 + ON DELETE 無し）
    conn = op.get_bind()
    try:
        op.drop_constraint('event_log_page_id_fkey', 'event_log', type_='foreignkey')
    except Exception:
        res = conn.execute(sa.text("""
            SELECT conname FROM pg_constraint c
            JOIN pg_class r ON r.oid = c.conrelid
            WHERE r.relname = 'event_log' AND conname LIKE '%page_id%fkey%'
        """)).fetchall()
        for row in res:
            try:
                op.drop_constraint(row[0], 'event_log', type_='foreignkey')
            except Exception:
                pass
    op.create_foreign_key('event_log_page_id_fkey', 'event_log', 'spots', ['page_id'], ['id'])
    op.alter_column('event_log', 'page_id', existing_type=sa.BigInteger(), nullable=False)


