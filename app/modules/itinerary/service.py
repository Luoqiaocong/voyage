from typing import Annotated, Any

from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.business import BusinessCode, ItineraryException
from app.modules.conversation.gateway import ConversationGateway
from app.shared.db import get_db
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
        
        
    async def check_authorization(self, user_id: int, itinerary_id: int):
        itinerary = await self.repo.check(itinerary_id)
        if not (itinerary and itinerary.user_id == user_id):
            raise ItineraryException(BusinessCode.ITINERARY_NOT_FOUND)
        
        
    async def _get_itinerary_base(self, itinerary_id: int):
        itinerary_plan = await self.repo.get(itinerary_id)
        if not itinerary_plan:
            raise ItineraryException(BusinessCode.ITINERARY_NOT_FOUND)
        return itinerary_plan

    async def save_itinerary_from_conversation(self, conversation_id: str,user_id: int):
        # 会话归属与存在的校验已由路由层 conversation 域的 verify_conversation_owner 完成，
        # service 只负责：读最后一条 AI 回复 → 结构化提取 → 落库。

        # 1. 获取数据
        recommend_text = await self.conv_gateway.get_last_ai_text(conversation_id)
        
        # 2. 结构化提取
        plan = await extract_itinerary_plan(recommend_text)
        
        # 3. 先检查是否成功
        if plan is None:
            raise ItineraryException(BusinessCode.ITINERARY_GEN_FAILED)
        
        # 4. 转换为字典
        plan_dict = plan.model_dump() if isinstance(plan, BaseModel) else plan
        
        # 5. 存入数据库
        async with self.transaction_scope():
            return await self.repo.insert(
                conversation_id=conversation_id,
                user_id=user_id,
                plan=plan_dict
            )
            
    async def get_itinerary(self, itinerary_id: int):
        return await self._get_itinerary_base(itinerary_id)
        
    async def update_itinerary(self,itinerary_id:int,plan:dict[str,Any]):
        """整体替换行程计划（PUT）：前端全量保存或 AI 续改结果落库。"""
        itinerary =  await self._get_itinerary_base(itinerary_id)
        async with self.transaction_scope():
            return await self.repo.update(itinerary,plan=plan)
        
    async def patch_itinerary(self, itinerary_id: int, patch: ItineraryPatch):
        """局部更新行程独立字段（PATCH）：预算/偏好/交通/提醒/住宿；派生字段不可改。

        合并（只取实际传入、且非 null 的字段）后整体校验落库，避免产生结构性脏数据。
        """
        """更新行程独立字段：合并后整体校验落库，派生字段不会受影响。"""
        itinerary = await self._get_itinerary_base(itinerary_id)
        # 只取实际传入的字段；显式传 null 视为「不修改」，避免写入非法结构
        changes = {
            k: v
            for k, v in patch.model_dump(exclude_unset=True).items()
            if v is not None
        }
        merged = {**itinerary.plan, **changes} #  itinerary.plan 在数据库中存的是字典类型
        validated = ItineraryPlan.model_validate(merged) # 先按规则检查，不合规就报错
        async with self.transaction_scope():
            return await self.repo.update(itinerary, plan=validated.model_dump())
        
        
    async def delete_itinerary(self, itinerary_id: int):
        async with self.transaction_scope():
            is_deleted = await self.repo.remove(itinerary_id)
        if not is_deleted:
            raise ItineraryException(BusinessCode.ITINERARY_DELETED_FAILED)
        
        