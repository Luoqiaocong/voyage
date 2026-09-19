"""add user_token_usage table

按「用户 × 日期」聚合的 Token 用量表，供管理端的 Token 用量排行使用。

为什么单独建表而不是给 token_usage 加一列 user_id：
    两者是**不同的聚合维度**——token_usage 是「模型 × 日期」，
    本表是「用户 × 日期」。合并会让唯一键变成 (user, model, date)，
    其中 user_id 必须可空（模型维度的行不属于任何用户），
    一个可空列参与唯一约束会让 upsert 的「冲突即累加」语义难以推理；
    且现有看板的所有聚合查询都要跟着改，回归风险不小。

历史数据：本表从引入时开始累积。token_usage 里已有的用量没有用户维度、
无法拆分到用户，故不出现在排行中 —— 已知且无法弥补。

Revision ID: b8f3c1d92e47
Revises: a222c2af2cbd
Create Date: 2026-09-19
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8f3c1d92e47"
down_revision: Union[str, None] = "a222c2af2cbd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_token_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="所属用户ID"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0",
                  comment="输入 token 数"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0",
                  comment="输出 token 数"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0",
                  comment="总 token 数"),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0",
                  comment="LLM 调用次数"),
        sa.Column("record_date", sa.String(length=10), nullable=False,
                  comment="统计日期 yyyy-MM-dd（本地时区）"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  comment="创建时间（UTC）"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        # 唯一键是 upsert「冲突即累加」的依据，必须与 ORM 定义一致，
        # 否则落库时会不断插入新行而不是累加
        sa.UniqueConstraint("user_id", "record_date", name="uq_user_date"),
    )
    op.create_index("ix_user_token_usage_user_id", "user_token_usage", ["user_id"])
    op.create_index("ix_user_token_usage_record_date", "user_token_usage", ["record_date"])


def downgrade() -> None:
    op.drop_index("ix_user_token_usage_record_date", table_name="user_token_usage")
    op.drop_index("ix_user_token_usage_user_id", table_name="user_token_usage")
    op.drop_table("user_token_usage")
