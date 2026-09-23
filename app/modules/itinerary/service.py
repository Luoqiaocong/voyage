from typing import Annotated, Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.business import BusinessCode, ItineraryException
from app.modules.conversation.gateway import ConversationGateway
from app.shared.db import get_db
from app.shared.ratelimit import (
    EXTRACT_USER_LIMIT,
    EXTRACT_USER_WINDOW,
    check_rate_limit,
    extract_user_key,
)
from app.shared.redis import redis_client
from app.shared.utils import TransactionMixin

from .extractor import extract_itinerary_plan
from .repo import ItineraryRepo
from .schemas import ItineraryPatch, ItineraryPlan


class ItineraryService(TransactionMixin):
    def __init__(
        self,
        repo: Annotated[ItineraryRepo, Depends()],
        conv_gateway: Annotated[ConversationGateway, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        self.repo = repo
        self.conv_gateway = conv_gateway
        self.db = db

    # ---------- 鉴权 ----------
    async def check_authorization(self, user_id: int, itinerary_id: int):
        """校验行程存在且属于当前用户；否则统一视为行程不存在。"""
        itinerary = await self.repo.get(itinerary_id)
        if not (itinerary and itinerary.user_id == user_id):
            raise ItineraryException(BusinessCode.ITINERARY_NOT_FOUND)

    async def _get_itinerary_base(self, itinerary_id: int):
        """查询行程并确保存在；不存在抛行程不存在异常。"""
        itinerary_plan = await self.repo.get(itinerary_id)
        if not itinerary_plan:
            raise ItineraryException(BusinessCode.ITINERARY_NOT_FOUND)
        return itinerary_plan

    # ---------- 生成与保存 ----------
    # 模型在「无内容可提取」时会硬凑出的占位目的地。
    #
    # 这个判定踩过两次坑，结论是：**中文不能用子串/前缀匹配**。
    #   第一次：枚举完整词表（待定/未知/…），模型改说「待确认」就漏了
    #   第二次：改成「待/未/无」等前缀匹配，把「无锡」这种正常城市名误伤
    #     （「无」出现在词首，但整词是地名）
    # 占位词与地名在中文里天然重叠，字符串匹配无法可靠区分，故只保留
    # 「完整相等」这一种匹配。真正扛起判定责任的是下面的结构条件 2 ——
    # 无内容可提取时模型给出的产物必然是退化的（1 天且 0 活动），
    # 这一点与它用什么占位词无关，因此稳定。
    _PLACEHOLDER_EXACT = frozenset(
        {
            "待定", "待确认", "待补充", "待商定", "待提供",
            "未知", "未指定", "未提供", "暂无", "无", "不详", "不确定",
            "-", "—", "n/a", "na", "none", "null", "tbd", "unknown",
        }
    )

    @classmethod
    def _is_placeholder_destination(cls, dest: str) -> bool:
        """目的地是否为占位表达。

        只做完整相等匹配——理由见上方注释，中文子串匹配会误伤地名。
        """
        d = (dest or "").strip().lower()
        return (not d) or (d in cls._PLACEHOLDER_EXACT)

    @classmethod
    def _looks_fabricated(cls, plan: ItineraryPlan) -> bool:
        """判断抽取结果是否为「无内容可提取时的硬凑产物」。

        判定依据（任一命中即认为是硬凑）：
          1. 目的地是占位表达（待定 / 待确认 / 未知 / TBD …）
          2. 日计划只有 1 个且活动总数为 0 —— 真正的行程至少有一个活动安排

        为什么需要这道检查：抽取接口的本职是把**已有**攻略转成结构化数据。
        当输入本就没有行程时，模型不会返回失败，而是尽力编一份最小的，
        结果是用户账户里多出一份「待定 · 1 天」的垃圾行程，
        比直接报错更糟——用户会以为提取成功了。
        """
        if cls._is_placeholder_destination(plan.destination):
            return True
        activity_count = sum(len(day.activities or []) for day in (plan.daily_plans or []))
        if len(plan.daily_plans or []) <= 1 and activity_count == 0:
            return True
        return False

    async def save_from_conversation(
        self,
        conversation_id: str,
        user_id: int,
        *,
        overwrite: bool = False,
    ):
        # 会话归属与存在的校验已由路由层 conversation 域的 verify_conversation_owner 完成，
        # service 只负责：总结会话历史 → 结构化提取 → 落库。
        lock_key = f"itinerary:extract:{user_id}:{conversation_id}"
        redis = redis_client.get_client()
        acquired = await redis.set(lock_key, "1", nx=True, ex=180)
        if not acquired:
            raise ItineraryException(BusinessCode.ITINERARY_EXTRACT_BUSY)

        try:
            # 用户维度配额：放在拿到会话锁之后，这样「同会话并发被锁挡掉」
            # 的请求不会白扣一次额度。计次覆盖成功与失败两种结果 ——
            # 无论提取是否成功，模型都已经被调用过，成本已经产生。
            if await check_rate_limit(
                extract_user_key(user_id), EXTRACT_USER_LIMIT, EXTRACT_USER_WINDOW
            ):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="行程提取过于频繁，请稍后再试",
                    headers={"Retry-After": str(EXTRACT_USER_WINDOW)},
                )

            transcript = await self.conv_gateway.get_conversation_transcript(conversation_id)
            if not transcript.strip():
                raise ItineraryException(BusinessCode.ITINERARY_GEN_FAILED)

            plan = await extract_itinerary_plan(transcript)
            if plan is None or self._looks_fabricated(plan):
                raise ItineraryException(BusinessCode.ITINERARY_GEN_FAILED)

            plan_dict = plan.model_dump() if isinstance(plan, BaseModel) else plan

            async with self.transaction_scope():
                existing = await self.repo.get_latest_by_conversation(user_id, conversation_id)
                if overwrite and existing is not None:
                    return await self.repo.update(existing, plan=plan_dict)
                return await self.repo.insert(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    plan=plan_dict,
                )
        finally:
            await redis.delete(lock_key)

    # ---------- 查询 ----------
    async def get_itineraries_page(
        self,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = 12,
        q: str | None = None,
    ):
        return await self.repo.list_by_user_page(
            user_id, page=page, page_size=page_size, q=q
        )

    async def count_itineraries(self, user_id: int) -> int:
        return await self.repo.count_by_user(user_id)

    async def get_latest_for_conversation(self, user_id: int, conversation_id: str):
        return await self.repo.get_latest_by_conversation(user_id, conversation_id)

    async def get_itinerary(self, itinerary_id: int):
        """查询单个行程详情。"""
        return await self._get_itinerary_base(itinerary_id)

    # ---------- 更新 ----------
    async def update_itinerary(self, itinerary_id: int, plan: dict[str, Any]):
        """整体替换行程计划（PUT）：前端整体编辑后全量保存。"""
        itinerary = await self._get_itinerary_base(itinerary_id)
        async with self.transaction_scope():
            return await self.repo.update(itinerary, plan=plan)

    async def patch_itinerary(self, itinerary_id: int, patch: ItineraryPatch):
        """局部更新行程独立字段（PATCH）：预算/偏好/交通/提醒/住宿；派生字段不可改。

        合并（只取实际传入、且非 null 的字段）后整体校验落库，避免产生结构性脏数据。
        """
        itinerary = await self._get_itinerary_base(itinerary_id)
        # 只取实际传入的字段；显式传 null 视为「不修改」，避免写入非法结构
        changes = {
            k: v
            for k, v in patch.model_dump(exclude_unset=True).items()
            if v is not None
        }
        merged = {**itinerary.plan, **changes}  # 数据库中 plan 存的是字典
        validated = ItineraryPlan.model_validate(merged)  # 先按规则检查，不合规就报错
        async with self.transaction_scope():
            return await self.repo.update(itinerary, plan=validated.model_dump())

    # ---------- 删除 ----------
    async def delete_itinerary(self, itinerary_id: int):
        """删除行程；不存在或删除失败时抛异常。"""
        async with self.transaction_scope():
            is_deleted = await self.repo.remove(itinerary_id)
        if not is_deleted:
            raise ItineraryException(BusinessCode.ITINERARY_DELETED_FAILED)