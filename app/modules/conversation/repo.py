from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db import get_db
from app.shared.db.models import Conversation


class ConversationRepo:

    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]):
        self.db = db

    async def check(self, conversation_id: str):
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_owner_id(self, conversation_id: str) -> int | None:
        """只取会话所属用户 ID。

        对话链路需要它来加载该用户的长期记忆，而整行 Conversation 并无用处，
        故只查单列；比 check() 少取若干字段，也更明确调用意图。
        """
        return (
            await self.db.execute(
                select(Conversation.user_id).where(Conversation.id == conversation_id)
            )
        ).scalar_one_or_none()

    async def remove(self, conversation_ids: list[str]):
        stmt = delete(Conversation).where(Conversation.id.in_(conversation_ids))
        row = await self.db.execute(stmt)
        await self.db.flush()
        return row.rowcount  # type: ignore

    async def remove_owned(
        self, user_id: int, conversation_ids: list[str]
    ) -> list[str]:
        """删除属于该用户的会话行，返回**实际删除**的 id 列表。

        原实现先把该用户全部会话查出来取交集再删，O(全部会话)；这里把
        「归属校验」下沉到 DELETE 的 WHERE，越权或不存在的 id 被数据库直接过滤，
        代价与待删数量成正比。返回 id 供调用方随后清理 langgraph checkpoint——
        必须用真正删掉的 id，否则越权 id 会被用来清别人的 checkpoint。
        """
        if not conversation_ids:
            return []
        stmt = (
            delete(Conversation)
            .where(Conversation.id.in_(conversation_ids))
            .where(Conversation.user_id == user_id)
            .returning(Conversation.id)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        await self.db.flush()
        return list(rows)

    async def create(self, **kwargs) -> Conversation:
        conversation = Conversation(**kwargs)
        self.db.add(conversation)
        await self.db.flush()
        return conversation

    async def get_by_user_id(self, user_id: int):
        stmt = select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.created_at.desc())
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_conversation(self, conversation_id: str, updated_data: dict[str, Any]):
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(**updated_data)
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def increment_message_count(self, conversation_id: str) -> None:
        """消息数 +1（原子自增，不读回旧值）。

        原实现在 Python 侧 `count = count + 1` 再整值写回，
        同一会话并发两条消息时会互相覆盖、丢掉一次计数。
        改为让数据库做 `message_count = message_count + 1`，天然原子。
        """
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(message_count=Conversation.message_count + 1)
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def get_empty_conversation(self, user_id: int):
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .where(Conversation.message_count == 0)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()