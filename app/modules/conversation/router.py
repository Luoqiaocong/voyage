import json
from typing import Annotated, AsyncGenerator
from fastapi import APIRouter, Body, Depends, Path
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
        summary="获取历史对话消息",
        dependencies=[Depends(verify_conversation_owner)],
    )
    async def get_messages(
        self,
        id: Annotated[ConversationId, Path()],
    ):
        # TODO: 
        # 消息按轮次返回：HumanMessage → AI/Tool → 下一条 HumanMessage 前
        return await self.service.get_messages(id)

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
        async for chunk in self.service.send_message(req.message, id):
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
    @router.delete(
        "/{id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="删除单个对话",
        dependencies=[Depends(verify_conversation_owner)],
        deprecated=True
    )
    async def delete_conversation(
        self,
        id: Annotated[ConversationId, Path()],
    ):
        await self.service.delete_conversation(id)
        
    @router.post(
        "/delete",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="批量删除对话",
    )
    async def delete_conversations(self, delete_req: ConversationIdsRequest):
        await self.service.delete_conversations_by_ids(self.current_user.id, delete_req.ids)