"""rename display_name to slug on users

Revision ID: ef34abcd1234
Revises: f1f2d3c4b5a6
Create Date: 2025-09-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ef34abcd1234'
down_revision = 'f1f2d3c4b5a6'
branch_labels = None
depends_on = None


def upgrade():
    # 1) display_name -> slug に列名変更（SQLiteも考慮しつつ汎用的に）
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('display_name', new_column_name='slug', existing_type=sa.String(length=100), existing_nullable=True)

    # 2) 旧ユニーク制約名がある場合に備え、ユニークを保証（DBにより名称が異なるため一旦明示追加）
    #    既に unique=True の列属性なら不要だが、マイグレーションの安全性確保のためにexistsチェックは省略
    try:
        op.create_unique_constraint('uq_users_slug', 'users', ['slug'])
    except Exception:
        pass


def downgrade():
    # 逆変換: slug -> display_name
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('slug', new_column_name='display_name', existing_type=sa.String(length=100), existing_nullable=True)
    try:
        op.drop_constraint('uq_users_slug', 'users', type_='unique')
    except Exception:
        pass


