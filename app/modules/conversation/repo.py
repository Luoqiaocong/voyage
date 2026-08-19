from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.models import Conversation
from app.shared.db.session import get_db

class ConversationRepo:
    
    
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]):
        self.db = db
            
    async def create(self,**kwargs)->Conversation:
        conversation = Conversation(**kwargs)
        self.db.add(conversation)
        await self.db.flush()
        return conversation
    
    async def check(self,conversation_id:str):
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result  = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def remove(self,conversation_id:str):
        stmt = delete(Conversation).where(Conversation.id == conversation_id)
        row =  await self.db.execute(stmt)
        await self.db.flush()
        return row.rowcount >0 # type: ignore