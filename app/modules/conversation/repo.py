from typing import Annotated

from fastapi import Depends
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