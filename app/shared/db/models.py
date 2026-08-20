from datetime import datetime

# ── ORM 语法基础（建议记牢）────────────────────────────────────
# Mapped[str]      : 类型标注，配合下方 mapped_column 声明列的类型
# mapped_column(...): 真正定义“这一列”的属性（类型/约束/索引等）
# ForeignKey       : 外键，建立表关联（如 conversations.user_id → users.id）
# relationship     : ORM 层的“对象关系”，用于 Python 侧便捷访问关联数据
#                    （它只影响 ORM 对象访问，不影响数据库表结构本身）
# ────────────────────────────────────────────────────────────────
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


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
        DateTime,
            default=datetime.now(),
            nullable=False,
            comment="创建时间（北京时间）",
        )
   
    conversations: Mapped[list["Conversation"]] = relationship(
           back_populates="user",
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
        DateTime,
        default=datetime.now(),
        nullable=False,
        comment="会话创建时间（北京时间）",
    )

    user: Mapped[User] = relationship(back_populates="conversations")
    # 与之配套的正向关联：conversation.user → 所属用户