


from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Any
from app.shared.db.models import Itinerary
from app.shared.db import get_db


class ItineraryRepo:
    def __init__(self,
                 db: Annotated[AsyncSession, Depends(get_db)]) -> None:
        self.db = db
        
        
    async def check(self, itinerary_id: int):
        stmt = select(Itinerary).where(Itinerary.id == itinerary_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
        
    async def insert(self,conversation_id:str,user_id:int,plan:dict[str,Any],**kwargs):
        itinerary = Itinerary(
            conversation_id=conversation_id,
            user_id=user_id,
            plan=plan,
            **kwargs
        )
        self.db.add(itinerary)
        await self.db.flush()
        return itinerary
    
    
    async def get(self,itinerary_id:int):
        stmt = select(Itinerary).where(Itinerary.id == itinerary_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    
    async def update(self, itinerary:Itinerary,plan:dict[str,Any]):
        itinerary.plan = plan
        await self.db.flush()
        return itinerary
    
    async def remove(self, itinerary_id: int):
        stmt = delete(Itinerary).where(Itinerary.id == itinerary_id)
        row = await self.db.execute(stmt)
        await self.db.flush()
        return row.rowcount > 0 # type: ignore