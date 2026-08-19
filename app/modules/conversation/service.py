from datetime import datetime
from typing import Annotated

from fastapi import Depends

from app.shared.db.session import get_db

from sqlalchemy.ext.asyncio import AsyncSession
from  .util import get_id
from  app.shared.utils import TransactionMixin
from .repo import ConversationRepo
from .gateway import ConversationGateway

# ===================== 已知设计限制（TODO）=====================
# 1. 会话 id 未落库、未与用户绑定：
#    - create_conversation 只生成一个 uuid(LangGraph thread_id)，不写入任何注册表，
#      因此“会话是否真的创建过”目前无法校验 → 任意符合 ^[a-zA-Z0-9]{12}$ 的 id 都能通过。
#    - 这是刻意为之：当前不想为“纯存在性校验”单独建表，将来做用户模块 + 会话落库(SQL)时
#      会由 user_id + conversation 表一并解决，届时再补 existence/ownership 校验。
# 2. 本文件所有按 conversation_id 操作的方法，将来都应先校验会话存在与归属。
# ==============================================================


class ConversationService(TransactionMixin):
    def __init__(
        self, 
        gateway: Annotated[ConversationGateway, Depends()],
        repo :Annotated[ConversationRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)]  # 掌握事务主动权                                         
    ) -> None:
        self.gateway = gateway
        self.repo = repo
        self.db = db

    async def send_message(self, message: str, conversation_id: str):
        async for chunk in self.gateway.stream_message(message, conversation_id):
            yield chunk

    async def get_messages(self, conversation_id: str, **kwargs):
        return await self.gateway.get_messages(conversation_id, **kwargs)

    async def delete_conversation(self, conversation_id: str):
        return await self.gateway.delete_conversation_thread(conversation_id)
    
    async def create_conversations(self,user_id:int):
        conversation_id = get_id()
        async with self.transaction_scope():
            return await self.repo.create(user_id=user_id,id=conversation_id, title=f"会话 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
