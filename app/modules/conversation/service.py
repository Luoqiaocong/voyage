from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business.code import BusinessCode
from app.core.business.exception import ConversationException
from app.shared.db.models import Conversation
from app.shared.db.session import get_db
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
                title=f"会话 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            )

    # -------------------- 2. 查询列表 --------------------
    async def get_conversations(self, user_id: int):
        return await self.repo.get(user_id)

    # -------------------- 3. 查询历史消息 --------------------
    async def get_messages(self, conversation_id: str, **kwargs):
        return await self.gateway.get_messages(conversation_id, **kwargs)

    # -------------------- 4. 流式发送消息 --------------------
    async def send_message(self, message: str, conversation_id: str):
        async for chunk in self.gateway.stream_message(message, conversation_id):
            yield chunk

    # -------------------- 5. 删除 --------------------
    async def delete_conversation(self, conversation_id: str):
        # 先删除内存会话再删除数据库会话数据,还是要事务处理，如果某一个环节崩了会有残留
        await self.gateway.delete_conversation_thread(conversation_id)
        async with self.transaction_scope():
            await self.repo.remove(conversation_id)
