from datetime import datetime, timezone

# ── ORM 语法基础（建议记牢）────────────────────────────────────
# Mapped[str]      : 类型标注，配合下方 mapped_column 声明列的类型
# mapped_column(...): 真正定义“这一列”的属性（类型/约束/索引等）
# ForeignKey       : 外键，建立表关联（如 conversations.user_id → users.id）
# relationship     : ORM 层的“对象关系”，用于 Python 侧便捷访问关联数据
#                    （它只影响 ORM 对象访问，不影响数据库表结构本身）
# ────────────────────────────────────────────────────────────────
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

def utc_now():
    """返回当前 UTC 时间（供 default 使用）"""
    return datetime.now(timezone.utc)


class User(Base):
    """用户表。"""
    __tablename__ = "users"   # 数据库表名（不然会用类名默认）

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="用户ID")
    
    email: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True, comment="用户邮箱")
    
    username: Mapped[str] = mapped_column(
            String(64), index=True, nullable=False
        )
    
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    avatar: Mapped[str] = mapped_column(
        String(255),
        default="photographer.png",
        comment="头像文件名（不含域名，如 photographer.png）"
    )

    # relationship : 让 Python 侧能用 user.conversations 拿到该用户的所有会话
    # back_populates: 关联到 Conversation.user，二者互为反向
    # cascade       : 删用户时级联删其会话(all, delete-orphan)
    created_at: Mapped[datetime] = mapped_column(
         DateTime(timezone=True),
            default=utc_now,
            nullable=False,
            comment="创建时间（UTC）",
        )
   
    conversations: Mapped[list["Conversation"]] = relationship(
           back_populates="user", # 双向关系的另一侧：在 Conversation 模型中，对应的属性叫 user
           cascade="all, delete-orphan",
       )


class Conversation(Base):
    """会话表：让会话有归属（user_id）——解决"会话无法校验存在性"的缺口。"""
    __tablename__ = "conversations"

    # id 沿用现有 12 位 hex conversation_id
    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="会话ID")
    # 用 conversation_id 作主键 → 可以用 SELECT...WHERE id=? 判断“存不存在”
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="用户ID",
    )
    # ForeignKey("users.id") : 外键指向 users 表的 id 列
    # ondelete="CASCADE"     : 用户在数据库层删除时，其会话也级联删除
    # index=True             : 按 user 查会话更快
    title: Mapped[str | None] = mapped_column(String(255), nullable=True,comment="会话标题")
    # str | None + nullable=True：该列允许 NULL（会话标题可空）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        comment="会话创建时间（UTC）",
    )
    
    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="会话消息数",
    )

    user: Mapped[User] = relationship(back_populates="conversations")
    
    itineraries: Mapped[list["Itinerary"]] = relationship(
        back_populates="conversation", # 双向关系的另一侧：在 Itinerary 模型中，对应的属性叫 conversation
        passive_deletes=True,  # 删除时由数据库处理关联，SQLAlchemy 不额外查询
    )
    # 一个会话可保存多份行程；删除会话不影响已保存的行程（行程是用户资产）


class Itinerary(Base):
    """行程表：一次「保存」的完整行程计划，plan 列存 ItineraryPlan 的 JSON。"""
    __tablename__ = "itineraries"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="行程ID"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="所属用户ID（行程独立归属用户，删除用户时级联删除）",
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="来源会话ID（12位hex）；会话删除后置空，行程保留",
    )
    plan: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="行程计划 JSON（ItineraryPlan：destination/days/daily_plans/tips 等）",
    )
    created_at: Mapped[datetime] = mapped_column(
         DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        comment="创建时间（UTC）",
    )
    updated_at: Mapped[datetime] = mapped_column(
         DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        comment="更新时间（UTC），保存后再次编辑时自动刷新",
    )

    conversation: Mapped[Conversation | None] = relationship(back_populates="itineraries")