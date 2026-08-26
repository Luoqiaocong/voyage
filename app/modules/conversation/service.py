from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.llm_tools import generate_conversation_title
from app.core.business import BusinessCode, ConversationException
from app.shared.db import get_db
from app.shared.utils import TransactionMixin

from .util import get_id
from .repo import ConversationRepo
from .gateway import ConversationGateway


class ConversationService(TransactionMixin):
    def __init__(
        self,
        gateway: Annotated[ConversationGateway, Depends()],
        repo: Annotated[ConversationRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)]  # 掌握事务主动权
    ) -> None:
        self.gateway = gateway
        self.repo = repo
        self.db = db

    async def check_authorization(self, *, user_id: int, conversation_id: str):
        conv = await self.repo.check(conversation_id)
        if not conv:
            raise ConversationException(code=BusinessCode.CONVERSATION_NOT_FOUND)
        if user_id != conv.user_id:
            raise ConversationException(code=BusinessCode.CONVERSATION_PERMISSION_DENIED)

    # -------------------- 1. 创建 --------------------
    async def create_conversations(self, user_id: int):
        conversation_id = get_id()
        async with self.transaction_scope():
            return await self.repo.create(
                user_id=user_id,
                id=conversation_id,
            )

    # -------------------- 2. 查询列表 --------------------
    async def get_conversations(self, user_id: int):
        return await self.repo.get_by_user_id(user_id)

    async def need_title(self, conversation_id: str) -> bool:
        """尚未有标题时返回 True（首个对话后触发一次自动生成）。"""
        conversation = await self.repo.check(conversation_id)
        return bool(conversation and not conversation.title)

    # -------------------- 3. 查询历史消息 --------------------
    async def get_messages(self, conversation_id: str, **kwargs):
        return await self.gateway.get_messages(conversation_id, **kwargs)

    # -------------------- 4. 流式发送消息 --------------------
    async def send_message(self, message: str, conversation_id: str):
        ai_text = ""
        async for chunk in self.gateway.stream_message(message, conversation_id):
            if chunk.get("type") == "text":
                ai_text += chunk.get("content", "")
            yield chunk

        # 本轮没有正常文本回复或已有标题时，不生成标题
        if not ai_text or not await self.need_title(conversation_id):
            return

        full_text = f"用户消息：{message}\nAI回复：{ai_text}"
        try:
            title = await generate_conversation_title(full_text)
        except Exception:
            return  # 标题生成失败不影响对话主流程
        async with self.transaction_scope():
            await self.repo.update(conversation_id, title)
        yield {"type": "title", "content": title}

    async def update_title(self, conversation_id: str, title: str):
        async with self.transaction_scope():
            await self.repo.update(conversation_id, title)

    # -------------------- 5. 删除 --------------------
    async def delete_conversation(self, conversation_id: str):
        # 先删除内存会话再删除数据库会话数据,还是要事务处理，如果某一个环节崩了会有残留
        await self.gateway.delete_conversation(conversation_id)
        async with self.transaction_scope():
            is_deleted = await self.repo.remove(conversation_id)
        if not is_deleted:
            raise ConversationException(BusinessCode.CONVERSATION_DELETED_FAILED)

    async def delete_conversations_for_user(self, user_id: int) -> None:
        """注销辅助：清理该用户所有会话的 langgraph 线程（DB 会话行由 users 级联删除）。"""
        conversations = await self.repo.get_by_user_id(user_id)
        await self.gateway.delete_conversation_batch([c.id for c in conversations])