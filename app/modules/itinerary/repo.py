from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import and_, delete, func, or_, select
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

    async def count_by_user(self, user_id: int) -> int:
        """用户行程总数（个人主页足迹数字用，避免拉全量）。"""
        stmt = select(func.count()).select_from(Itinerary).where(Itinerary.user_id == user_id)
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def list_by_user_page(
        self,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = 12,
        q: str | None = None,
    ) -> tuple[list[Itinerary], int]:
        """分页查询用户行程；q 按目的地模糊匹配。"""
        filters = [Itinerary.user_id == user_id]
        keyword = (q or "").strip()
        if keyword:
            like = f"%{keyword}%"
            filters.append(
                or_(
                    Itinerary.plan["destination"].as_string().ilike(like),
                    Itinerary.plan["transport"].as_string().ilike(like),
                )
            )
        where = and_(*filters)

        count_stmt = select(func.count()).select_from(Itinerary).where(where)
        total = int((await self.db.execute(count_stmt)).scalar_one() or 0)

        offset = max(page - 1, 0) * page_size
        list_stmt = (
            select(Itinerary)
            .where(where)
            .order_by(Itinerary.updated_at.desc(), Itinerary.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(list_stmt)).scalars().all()
        return list(rows), total

    async def get_latest_by_conversation(self, user_id: int, conversation_id: str):
        """该会话最近一份行程（用于覆盖前提示）。"""
        stmt = (
            select(Itinerary)
            .where(
                Itinerary.user_id == user_id,
                Itinerary.conversation_id == conversation_id,
            )
            .order_by(Itinerary.updated_at.desc(), Itinerary.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

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