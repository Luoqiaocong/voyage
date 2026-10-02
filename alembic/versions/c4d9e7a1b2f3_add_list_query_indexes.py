"""add composite indexes for conversation/itinerary list queries

会话列表与行程列表都按「用户 + 时间倒序」查询：
    conversations: WHERE user_id = ? ORDER BY created_at DESC
    itineraries:   WHERE user_id = ? ORDER BY updated_at DESC

原先只有 user_id 单列索引，排序仍需在取出的行上做；随着单个用户的数据增长，
会退化为「取出该用户全部行再排序」。这里补上复合索引，让过滤与排序共用同一索引。

PostgreSQL / SQLite 均使用 B-tree，升序索引对 DESC 排序同样可用（可反向扫描），
故无需显式指定排序方向。

Revision ID: c4d9e7a1b2f3
Revises: b8f3c1d92e47
Create Date: 2026-09-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4d9e7a1b2f3"
down_revision: Union[str, None] = "b8f3c1d92e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_conversations_user_created",
        "conversations",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_itineraries_user_updated",
        "itineraries",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_itineraries_user_updated", table_name="itineraries")
    op.drop_index("ix_conversations_user_created", table_name="conversations")
