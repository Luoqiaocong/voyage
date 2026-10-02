"""行程分享的数据访问层。

独立于 ItineraryRepo：分享是独立聚合（有自己的令牌、权限、过期与访问计数），
混进行程 repo 会让职责变模糊。
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db import get_db
from app.shared.db.models import ItineraryShare, User


class ShareRepo:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
        self.db = db

    # ---------- 查询 ----------
    async def get_by_token(self, token: str) -> ItineraryShare | None:
        """按令牌查分享。令牌全局唯一，命中即可确定目标行程。"""
        return (
            await self.db.execute(
                select(ItineraryShare).where(ItineraryShare.token == token)
            )
        ).scalar_one_or_none()

    async def get_by_id(self, share_id: int) -> ItineraryShare | None:
        return (
            await self.db.execute(
                select(ItineraryShare).where(ItineraryShare.id == share_id)
            )
        ).scalar_one_or_none()

    async def list_by_itinerary(self, itinerary_id: int) -> list[ItineraryShare]:
        """某行程的全部分享链接（按创建时间倒序）。"""
        rows = await self.db.execute(
            select(ItineraryShare)
            .where(ItineraryShare.itinerary_id == itinerary_id)
            .order_by(ItineraryShare.created_at.desc(), ItineraryShare.id.desc())
        )
        return list(rows.scalars().all())

    async def list_by_owner(self, owner_id: int) -> list[ItineraryShare]:
        """某人创建的全部分享链接（跨行程），便于集中管理与撤销。"""
        rows = await self.db.execute(
            select(ItineraryShare)
            .where(ItineraryShare.owner_id == owner_id)
            .order_by(ItineraryShare.created_at.desc())
        )
        return list(rows.scalars().all())

    async def get_owner(self, owner_id: int) -> User | None:
        """取分享者信息（用于在分享页展示「谁分享的」）。"""
        return (
            await self.db.execute(select(User).where(User.id == owner_id))
        ).scalar_one_or_none()

    # ---------- 写入 ----------
    async def insert(self, **fields) -> ItineraryShare:
        share = ItineraryShare(**fields)
        self.db.add(share)
        await self.db.flush()
        return share

    async def bump_view_count(self, share: ItineraryShare) -> int:
        """访问计数 +1，返回自增后的值。

        用数据库侧 `view_count = view_count + 1 RETURNING view_count`，
        而不是「读取-加一-写回」：同一条链接被并发打开时后者会互相覆盖，
        丢计数。单条 UPDATE 由数据库保证原子性，返回值为最新计数。
        """
        stmt = (
            update(ItineraryShare)
            .where(ItineraryShare.id == share.id)
            .values(view_count=ItineraryShare.view_count + 1)
            .returning(ItineraryShare.view_count)
        )
        new_count = (await self.db.execute(stmt)).scalar_one()
        await self.db.flush()
        return int(new_count)

    async def delete(self, share: ItineraryShare) -> None:
        """物理删除分享记录。

        为什么是删除而不是置 revoked_at：
        - 对外的接口就是 DELETE /itineraries/shares/{id}，语义上应当删除
        - 原先只置失效，导致记录仍留在列表里，用户以为「删不掉」
        - 链接一旦撤销就已失效，保留失效记录的追溯价值很低；
          真正需要留痕的是管理端操作，那由 admin_audit_log 负责
        """
        await self.db.delete(share)
        await self.db.flush()
