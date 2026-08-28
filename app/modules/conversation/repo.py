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

    async def remove(self, conversation_ids: list[str]):
        stmt = delete(Conversation).where(Conversation.id.in_(conversation_ids))
        row = await self.db.execute(stmt)
        await self.db.flush()
        return row.rowcount  # type: ignore

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

    async def get_empty_conversation(self, user_id: int):
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .where(Conversation.message_count == 0)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()