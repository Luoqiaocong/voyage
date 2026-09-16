"""管理端数据访问层。"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db import get_db
from app.shared.db.models import Conversation, Itinerary, TokenUsage, User


class AdminRepo:
    """管理端查询（只读为主 + 少量写操作，写操作的审计由 service 负责）。"""

    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
        self.db = db

    # -------------------- 用户 --------------------
    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        """分页查询用户，支持邮箱/昵称关键词与角色、状态筛选。"""
        conditions = []
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(User.email.ilike(like), User.username.ilike(like)))
        if role:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)

        count_stmt = select(func.count(User.id))
        list_stmt = select(User)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
            list_stmt = list_stmt.where(cond)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        list_stmt = (
            list_stmt.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        rows = list((await self.db.execute(list_stmt)).scalars().all())
        return rows, total

    async def get_user(self, user_id: int) -> User | None:
        return (
            await self.db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()

    async def user_usage_counts(self, user_id: int) -> tuple[int, int]:
        """返回 (会话数, 行程数)。"""
        conversations = (
            await self.db.execute(
                select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
            )
        ).scalar_one()
        itineraries = (
            await self.db.execute(
                select(func.count(Itinerary.id)).where(Itinerary.user_id == user_id)
            )
        ).scalar_one()
        return int(conversations), int(itineraries)

    async def count_admins(self) -> int:
        """当前启用状态的管理员数量（用于「不能停用最后一个管理员」的保护）。"""
        return int(
            (
                await self.db.execute(
                    select(func.count(User.id)).where(
                        User.role == "admin", User.is_active.is_(True)
                    )
                )
            ).scalar_one()
        )

    # -------------------- 会话洞察 --------------------
    async def conversation_stats(self) -> dict:
        total_conversations = (
            await self.db.execute(select(func.count(Conversation.id)))
        ).scalar_one()
        total_messages = (
            await self.db.execute(select(func.coalesce(func.sum(Conversation.message_count), 0)))
        ).scalar_one()
        with_title = (
            await self.db.execute(
                select(func.count(Conversation.id)).where(Conversation.title.is_not(None))
            )
        ).scalar_one()

        top_rows = (
            await self.db.execute(
                select(Conversation.user_id, func.count(Conversation.id).label("n"))
                .group_by(Conversation.user_id)
                .order_by(func.count(Conversation.id).desc())
                .limit(5)
            )
        ).all()
        user_ids = [r[0] for r in top_rows]
        emails: dict[int, str] = {}
        if user_ids:
            user_rows = (
                await self.db.execute(
                    select(User.id, User.email).where(User.id.in_(user_ids))
                )
            ).all()
            emails = {r[0]: r[1] for r in user_rows}

        total_conv = int(total_conversations)
        total_msg = int(total_messages)
        return {
            "total_conversations": total_conv,
            "total_messages": total_msg,
            "avg_messages_per_conversation": round(total_msg / total_conv, 2) if total_conv else 0.0,
            "conversations_with_title": int(with_title),
            "top_active_users": [
                {"user_id": r[0], "email": emails.get(r[0], "未知"), "conversations": int(r[1])}
                for r in top_rows
            ],
        }

    async def list_conversations(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        user_id: int | None = None,
    ) -> tuple[list[dict], int]:
        """分页查询会话（附带用户邮箱），供管理端内容检索。"""
        conditions = []
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(Conversation.title.ilike(like))
        if user_id:
            conditions.append(Conversation.user_id == user_id)

        count_stmt = select(func.count(Conversation.id))
        list_stmt = (
            select(
                Conversation.id,
                Conversation.user_id,
                User.email,
                Conversation.title,
                Conversation.message_count,
                Conversation.created_at,
            )
            .join(User, User.id == Conversation.user_id)
        )
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
            list_stmt = list_stmt.where(cond)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        list_stmt = (
            list_stmt.order_by(Conversation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(list_stmt)).all()
        items = [
            {
                "id": r[0],
                "user_id": r[1],
                "user_email": r[2],
                "title": r[3],
                "message_count": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]
        return items, total

    # -------------------- 导出 --------------------
    async def iter_users_for_export(self):
        """流式导出用户（分批 yield，避免一次性载入全部行）。"""
        stmt = select(
            User.id, User.email, User.username, User.role, User.is_active, User.created_at
        ).order_by(User.id)
        result = await self.db.stream(stmt)
        async for row in result:
            yield row

    async def iter_token_usage_for_export(self):
        """流式导出用量明细。"""
        stmt = select(
            TokenUsage.record_date,
            TokenUsage.model,
            TokenUsage.input_tokens,
            TokenUsage.output_tokens,
            TokenUsage.total_tokens,
            TokenUsage.calls,
        ).order_by(TokenUsage.record_date.desc(), TokenUsage.model)
        result = await self.db.stream(stmt)
        async for row in result:
            yield row
