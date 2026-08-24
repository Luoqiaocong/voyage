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
        
