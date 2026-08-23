from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.structured import extract_itinerary_plan
from app.core.business import BusinessCode, ItineraryException
from app.modules.conversation.gateway import ConversationGateway
from app.shared.db.session import get_db
from app.shared.utils import TransactionMixin

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

    async def save_itinerary_from_conversation(self, conversation_id: str):
        # 会话归属与存在的校验已由路由层 conversation 域的 require_conversation_owner 完成，
        # service 只负责：读最后一条 AI 回复 → 结构化提取 → 落库。
        markdown = await self.conv_gateway.get_last_ai_text(conversation_id)
        plan = await extract_itinerary_plan(markdown)
        if plan is None:
            raise ItineraryException(BusinessCode.ITINERARY_GEN_FAILED)

        async with self.transaction_scope():
            return await self.repo.insert(conversation_id, plan.model_dump())