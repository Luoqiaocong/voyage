from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db import get_db
from app.shared.db.models import Itinerary


class ItineraryRepo:
    def __init__(
        self,
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> None:
        self.db = db

    # ---------- 查询 ----------
    async def get(self, itinerary_id: int):
        """按 ID 查询行程（鉴权用，不校验归属）。"""
        stmt = select(Itinerary).where(Itinerary.id == itinerary_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: int):
        """查询某用户的全部行程。"""
        stmt = select(Itinerary).where(Itinerary.user_id == user_id).order_by(Itinerary.created_at.desc())
        result = await self.db.execute(stmt)
        return result.scalars().all()

    # ---------- 写入 ----------
    async def insert(self, conversation_id: str, user_id: int, plan: dict[str, Any], **kwargs):
        """新增行程。"""
        itinerary = Itinerary(
            conversation_id=conversation_id,
            user_id=user_id,
            plan=plan,
            **kwargs,
        )
        self.db.add(itinerary)
        await self.db.flush()
        return itinerary

    async def update(self, itinerary: Itinerary, plan: dict[str, Any]):
        """整体替换行程计划内容（plan JSON）。"""
        itinerary.plan = plan
        await self.db.flush()
        return itinerary

    # ---------- 删除 ----------
    async def remove(self, itinerary_id: int):
        """按 ID 删除行程，返回是否删除成功。"""
        stmt = delete(Itinerary).where(Itinerary.id == itinerary_id)
        row = await self.db.execute(stmt)
        await self.db.flush()
        return (row.rowcount or 0) > 0  # type: ignore