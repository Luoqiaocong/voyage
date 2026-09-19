import json
from typing import Annotated, AsyncGenerator
from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute
from app.shared.annotations import ConversationId
from app.modules.user.dependencies import get_current_user
from app.shared.db.models import User
from .schemas import (
    ConversationMessageRequest,
    ConversationTitleRequest,
    ConversationResponse,
    UserConversationsResponse,
    ConversationIdsRequest
)
from .service import ConversationService
from .dependencies import verify_conversation_owner

# ===================== 路由定义 =====================
router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    route_class=UnifiedRoute,
)


@cbv(router)
class ConversationRouter:
    service: ConversationService = Depends()
    current_user: User = Depends(get_current_user)

    # -------------------- 1. 创建 --------------------
    @router.post(
        "/",
        status_code=status.HTTP_201_CREATED,
        summary="创建对话",
    )
    async def create_conversation(self):
        conversation = await self.service.create_conversation(self.current_user.id)
        return ConversationResponse.model_validate(conversation)

    # -------------------- 2. 查询列表 --------------------
    @router.get(
        "/",
        status_code=status.HTTP_200_OK,
        summary="获取对话列表",
    )
    async def get_conversations(self):
        conversations = await self.service.get_conversations(self.current_user.id)
        return UserConversationsResponse(
            conversations=[ConversationResponse.model_validate(c) for c in conversations]
        )

    # -------------------- 3. 查询历史消息 --------------------
    @router.get(
        "/{id}/messages",
        status_code=status.HTTP_200_OK,
        summary="获取历史对话消息（按轮次分页，字段已收敛）",
        dependencies=[Depends(verify_conversation_owner)],
    )
    async def get_messages(
        self,
        id: Annotated[ConversationId, Path()],
        limit: Annotated[
            int | None,
            Query(
                ge=1,
                le=200,
                description="返回最近多少轮对话（一轮=一条用户消息及其后的回复）；不传返回全部",
            ),
        ] = None,
    ):
        """按轮次返回历史消息。

        实现说明见 ConversationGateway.get_messages_page：
        - 按「轮次」截断而非按条截断，避免出现有回答没提问的断裂；
        - assistant 消息的 tool_calls 只保留工具名，剥掉模型的工具入参
          （前端渲染不需要，且属于内部调度细节）。
        """
        return await self.service.get_messages_page(id, limit=limit)

    # -------------------- 4. 流式发送消息 --------------------
    @router.post(
        "/{id}/messages",
        status_code=status.HTTP_200_OK,
        response_class=EventSourceResponse,
        summary="流式对话",
        dependencies=[Depends(verify_conversation_owner)],
    )
    async def send_message(
        self,
        id: Annotated[ConversationId, Path()],
        req: ConversationMessageRequest,
    ) -> AsyncGenerator[ServerSentEvent, None]:
        # 带上 user_id：Token 用量要按用户归属（LLM 回调在链路内部触发，
        # 只能经上下文变量读到它）
        async for chunk in self.service.send_message(req.message, id, self.current_user.id):
            yield ServerSentEvent(
                raw_data=json.dumps(chunk, ensure_ascii=False),
                event="message",
            )
        yield ServerSentEvent(raw_data="[DONE]", event="done")
        
    @router.patch(
        "/{id}",
        status_code=status.HTTP_200_OK,
        summary="更改会话标题",
        dependencies=[Depends(verify_conversation_owner)],
    )
    async def update_conversation_title(
        self,
        id: Annotated[ConversationId, Path()],
        req: ConversationTitleRequest,
    ):
        await self.service.update_title(id, req.title)
        
    # -------------------- 5. 删除 --------------------
    @router.post(
        "/delete",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="批量删除对话",
    )
    async def delete_conversations(self, delete_req: ConversationIdsRequest):
        await self.service.delete_conversations_by_ids(self.current_user.id, delete_req.ids)