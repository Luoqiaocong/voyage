from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.structured import extract_itinerary_plan
from app.core.business import BusinessCode, ConversationException, ItineraryException
from app.modules.conversation.gateway import ConversationGateway
from app.modules.conversation.repo import ConversationRepo
from app.shared.db.session import get_db
from app.shared.utils import TransactionMixin

from .repo import ItineraryRepo


def _last_assistant_text(messages: list[dict]) -> str:
    """取最后一条含文本内容的 AI 消息，跳过工具结果与空内容。"""
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return ""


class ItineraryService(TransactionMixin):
    def __init__(
        self,
        repo: Annotated[ItineraryRepo, Depends()],
        conversation_repo: Annotated[ConversationRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        self.repo = repo
        self.conversation_repo = conversation_repo
        self.db = db

    async def check_authorization(self, *, user_id: int, conversation_id: str):
        conv = await self.conversation_repo.check(conversation_id)
        if not conv:
            raise ConversationException(code=BusinessCode.CONVERSATION_NOT_FOUND)
        if user_id != conv.user_id:
            raise ConversationException(code=BusinessCode.CONVERSATION_PERMISSION_DENIED)

    async def save_itinerary_from_conversation(self, conversation_id: str):
        conv = await self.conversation_repo.check(conversation_id)
        if not conv:
            raise ConversationException(code=BusinessCode.CONVERSATION_NOT_FOUND)

        conv_gateway = ConversationGateway()
        messages = await conv_gateway.get_messages(conversation_id)
        output_recommend_json = await extract_itinerary_plan(_last_assistant_text(messages))
        if not output_recommend_json:
            raise ItineraryException(BusinessCode.ITINERARY_GEN_FAILED)
        async with self.transaction_scope():
            return await self.repo.insert(conversation_id, output_recommend_json.model_dump())