"""用户长期记忆的数据访问层。

冲突消解规则（本期技术重点）
--------------------------
唯一约束建在 (user_id, fact_key, fact_value) 上，让两类语义自动分流：

1. 重复提取（同一三元组再次出现）
   → 命中唯一约束，把 hit_count 加一并刷新时间。
   hit_count 越高说明该事实越稳定，注入 prompt 时可优先使用。

2. 标量键换值（budget_level 从「穷游」变成「舒适」）
   → 三元组不同，不会命中约束，但 fact_key 已被占用。
   此时按「同键覆盖」处理：把旧行的 fact_value 改成新值，
   旧值写入 previous_value 留痕。这样该键始终只有一条当前值。

3. 多值键新增（preference 新增「摄影」）
   → 同样不命中约束，但键属于多值类型，直接插入新行，与已有偏好并存。

区分 2 与 3 的依据是键的类型（SCALAR_KEYS / MULTI_KEYS），
而不是靠猜——这正是把键空间收窄成白名单的意义。
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memory.schemas import MULTI_KEYS
from app.shared.db import get_db
from app.shared.db.models import UserMemory


class MemoryRepo:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
        self.db = db

    # ---------- 查询 ----------
    async def list_by_user(
        self, user_id: int, *, include_inactive: bool = False
    ) -> list[UserMemory]:
        """列出某用户的记忆（默认只看生效中的）。

        排序：置信度降序 → 命中次数降序 → 更新时间降序。
        注入 prompt 时按此顺序取前 N 条，越靠前越可信、越常用。
        """
        stmt = select(UserMemory).where(UserMemory.user_id == user_id)
        if not include_inactive:
            stmt = stmt.where(UserMemory.is_active.is_(True))
        stmt = stmt.order_by(
            UserMemory.confidence.desc(),
            UserMemory.hit_count.desc(),
            UserMemory.updated_at.desc(),
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get(self, memory_id: int) -> UserMemory | None:
        return (
            await self.db.execute(
                select(UserMemory).where(UserMemory.id == memory_id)
            )
        ).scalar_one_or_none()

    async def find_scalar(self, user_id: int, fact_key: str) -> UserMemory | None:
        """取某标量键的当前值行（该键至多一行）。"""
        return (
            await self.db.execute(
                select(UserMemory).where(
                    UserMemory.user_id == user_id,
                    UserMemory.fact_key == fact_key,
                )
            )
        ).scalars().first()

    async def find_exact(
        self, user_id: int, fact_key: str, fact_value: str
    ) -> UserMemory | None:
        """按三元组精确查找（用于识别「重复提取到同一事实」）。"""
        return (
            await self.db.execute(
                select(UserMemory).where(
                    UserMemory.user_id == user_id,
                    UserMemory.fact_key == fact_key,
                    UserMemory.fact_value == fact_value,
                )
            )
        ).scalar_one_or_none()

    async def count_by_user(self, user_id: int) -> int:
        return int(
            (
                await self.db.execute(
                    select(func.count(UserMemory.id)).where(UserMemory.user_id == user_id)
                )
            ).scalar_one()
        )

    # ---------- 写入 ----------
    async def insert(self, **fields) -> UserMemory:
        memory = UserMemory(**fields)
        self.db.add(memory)
        await self.db.flush()
        return memory

    @staticmethod
    def is_multi_value_key(fact_key: str) -> bool:
        """该键是否允许同时存在多个取值。"""
        return fact_key in MULTI_KEYS
