"""add user_id to itineraries, conversation_id nullable / ON DELETE SET NULL

Revision ID: 6d4a9e02f185
Revises: 159f76bc0325
Create Date: 2026-08-23 22:10:00.000000

行程改为「用户资产」：新增 user_id（非空，FK users CASCADE）；
来源会话 conversation_id 改为可空 + ON DELETE SET NULL——
删除会话时行程保留，仅来源会话置空。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d4a9e02f185'
down_revision: Union[str, Sequence[str], None] = '159f76bc0325'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. 先加可空列（SQLite 不允许直接 ADD NOT NULL 无默认值的列）
    op.add_column('itineraries', sa.Column('user_id', sa.Integer(), nullable=True, comment='所属用户ID'))

    # 2. 回填存量数据：从来源会话取 user_id
    op.execute("""
        UPDATE itineraries
        SET user_id = (SELECT user_id FROM conversations WHERE conversations.id = itineraries.conversation_id)
        WHERE user_id IS NULL
    """)

    # 3. SQLite 重建表（六步法）：
    #    user_id 收紧为 NOT NULL + FK users CASCADE；
    #    conversation_id 改为可空 + FK conversations SET NULL
    op.execute("""
        CREATE TABLE itineraries_new (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            conversation_id VARCHAR(32),
            plan JSON NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT fk_itineraries_user_id FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
            CONSTRAINT fk_itineraries_conversation_id FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        INSERT INTO itineraries_new (id, user_id, conversation_id, plan, created_at, updated_at)
        SELECT id, user_id, conversation_id, plan, created_at, updated_at FROM itineraries
    """)
    op.execute("DROP TABLE itineraries")
    op.execute("ALTER TABLE itineraries_new RENAME TO itineraries")

    # 4. 重建索引（旧索引随旧表一起被删）
    op.create_index(op.f('ix_itineraries_user_id'), 'itineraries', ['user_id'], unique=False)
    op.create_index(op.f('ix_itineraries_conversation_id'), 'itineraries', ['conversation_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 还原：conversation_id 恢复 NOT NULL + ON DELETE CASCADE；去掉 user_id（存量 user_id 数据随之丢弃）
    op.execute("""
        CREATE TABLE itineraries_old (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            conversation_id VARCHAR(32) NOT NULL,
            plan JSON NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT fk_itineraries_conversation_id FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    """)
    # 已删除来源会话的行程无法还原 conversation_id，回滚时丢弃这些行
    op.execute("""
        INSERT INTO itineraries_old (id, conversation_id, plan, created_at, updated_at)
        SELECT id, conversation_id, plan, created_at, updated_at FROM itineraries
        WHERE conversation_id IS NOT NULL
    """)
    op.execute("DROP TABLE itineraries")
    op.execute("ALTER TABLE itineraries_old RENAME TO itineraries")
    op.create_index(op.f('ix_itineraries_conversation_id'), 'itineraries', ['conversation_id'], unique=False)