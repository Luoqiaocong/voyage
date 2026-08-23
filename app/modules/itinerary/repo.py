


from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Any
from app.shared.db.models import Itinerary
from app.shared.db.session import get_db


class ItineraryRepo:
    def __init__(self,
                 db: Annotated[AsyncSession, Depends(get_db)]) -> None:
        self.db = db
        
    async def insert(self,conversation_id:str,plan:dict[str,Any]):
        itinerary = Itinerary(conversation_id=conversation_id,plan=plan)
        self.db.add(itinerary)
        await self.db.flush()
        return itinerary