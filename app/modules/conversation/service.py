from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.tasks import generate_conversation_title
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
    async def create_conversation(self, user_id: int):
        """创建会话：已有空会话时直接复用，避免重复堆积。"""
        conversation = await self.repo.get_empty_conversation(user_id)
        if conversation:
            return conversation
        conversation_id = get_id()
        async with self.transaction_scope():
            return await self.repo.create(
                user_id=user_id,
                id=conversation_id,
            )

    # -------------------- 2. 查询列表 --------------------
    async def get_conversations(self, user_id: int):
        return await self.repo.get_by_user_id(user_id)

    # -------------------- 3. 查询历史消息 --------------------
    async def get_messages(self, conversation_id: str, **kwargs):
        return await self.gateway.get_messages(conversation_id, **kwargs)

    # -------------------- 4. 流式发送消息 --------------------
    async def send_message(self, message: str, conversation_id: str):
        ai_text = ""
        try:
            async for chunk in self.gateway.stream_message(message, conversation_id):
                if chunk.get("type") == "text":
                    ai_text += chunk.get("content", "")
                yield chunk
        except Exception as exc:
            # 流中途异常（模型/工具报错）：告知前端后正常收尾，避免连接悬挂
            print(f"[send_message] stream failed: {exc}")  # noqa: T201
            yield {"type": "error", "content": "AI 服务暂时不可用，请稍后重试"}
            return

        # 本轮没有正常文本回复时，不生成标题
        if not ai_text:
            return

        # 已有标题则不重复生成
        conversation = await self.repo.check(conversation_id)
        if conversation is None:
            raise ConversationException(code=BusinessCode.CONVERSATION_NOT_FOUND)

        updated_data = {}

        if not conversation.title:
            full_text = f"用户消息：{message}\nAI回复：{ai_text}"
            try:
                title = await generate_conversation_title(full_text)
                updated_data["title"] = title
            except Exception as exc:
                print(f"[send_message] title failed: {exc}")  # noqa: T201
            
            
        updated_data["message_count"] = conversation.message_count + 1

        async with self.transaction_scope():
            await self.repo.update_conversation(conversation_id, updated_data)

        if updated_data.get("title"):
            yield {"type": "title", "content": updated_data["title"]}

    async def update_title(self, conversation_id: str, title: str):
        async with self.transaction_scope():
            await self.repo.update_conversation(conversation_id, {"title": title})

    # -------------------- 5. 删除 --------------------
    async def delete_conversation(self, conversation_id: str):
        # 1. 先删业务行（事务内）：失败即整体失败，用户可重试，状态干净
        async with self.transaction_scope():
            deleted_count = await self.repo.remove([conversation_id])
        if deleted_count == 0:
            raise ConversationException(BusinessCode.CONVERSATION_DELETED_FAILED)

        # 2. 行删成功后再删 langgraph 线程：失败只留不可见孤儿数据，降级记录，不阻断
        try:
            await self.gateway.delete_conversation(conversation_id)
        except Exception as exc:
            print(f"[delete_conversation] thread cleanup failed: {conversation_id}: {exc}")  # noqa: T201


    async def _delete_conversations_batch_base(self, conversation_ids: list[str]):
        if not conversation_ids:
            return
        async with self.transaction_scope():
            await self.repo.remove(conversation_ids)
        results = await self.gateway.delete_conversation_batch(conversation_ids)
        for cid, result in zip(conversation_ids, results):
            if isinstance(result, Exception):
                print(f"[delete_conversations_by_user] thread cleanup failed: {cid}: {result}")  # noqa: T201

    async def delete_conversations_by_user(self, user_id: int) -> None:
        """注销辅助：先删该用户所有会话的业务行，再清 langgraph 线程（用户行由调用方级联删除）。"""
        conversations = await self.repo.get_by_user_id(user_id)
        conversation_ids = [c.id for c in conversations]
        await self._delete_conversations_batch_base(conversation_ids)
       

    async def delete_conversations_by_id(self, user_id: int, conversation_ids: list[str]):
        """批量删除会话：只删除属于当前用户的会话，其余 id 静默跳过。"""
        if not conversation_ids:
            return
        owned = await self.repo.get_by_user_id(user_id)
        own_ids = {c.id for c in owned}  # 得到当前用户持有的所有会话
        targets = [cid for cid in conversation_ids if cid in own_ids] # 取交集，如果不在交集内则跳过
        await self._delete_conversations_batch_base(targets)