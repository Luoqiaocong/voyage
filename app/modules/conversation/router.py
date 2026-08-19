import json
from collections.abc import AsyncIterable
from typing import Annotated
from fastapi import APIRouter, Depends, Path
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi_utils.cbv import cbv
from starlette import status
from app.core.route import UnifiedRoute
from app.modules.user.dependencies import get_current_user
from app.shared.db.models import User
from .schemas import (
    ConversationMessageRequest,
    ConversationResponse,
)
from .service import ConversationService

router = APIRouter(
    prefix="/conversations", tags=["conversation"], route_class=UnifiedRoute
)


async def verify(
    user:Annotated[User, Depends(get_current_user)],
    service:Annotated[ConversationService, Depends()],
    id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9]{12}$")],):
    await service.check_authorization(user_id=user.id,conversation_id=id)


@cbv(router)
class ConversationRouter:
    service: ConversationService = Depends()
    current_user: User = Depends(get_current_user)
    # ===================== TODO / 已知限制 =====================
    # 列表/分页：GET /conversations（按用户 id 拉全部）尚未实现；
    #    GET /{id}/messages 将来需支持 offset/limit 分批返回。
    # 消息按轮次返回：从一条 HumanMessage → AI/Tool → 至下一条 HumanMessage 前的分组。
    # =============================================================

    @router.get(
        "/{id}/messages",
        status_code=status.HTTP_200_OK,
        summary="获取历史对话消息",
        dependencies=[Depends(verify)]
    )
    async def get_messages(
        self,
        id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9]{12}$")],
        # offset: Annotated[int, Query(ge=1, description="消息跳过数量", alias="offset")],
        # limit: Annotated[int, Query(ge=2, le=50, description="消息数量", alias="limit")] = 10,
    ):
        return await self.service.get_messages(id)

    @router.delete(
         "/{id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="删除整个对话",
        dependencies=[Depends(verify)]
    )
    async def delete_conversation(
        self,
        id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9]{12}$")],
    ):
       return await self.service.delete_conversation(id)
   

    @router.post(
        "/",
        status_code=status.HTTP_201_CREATED,
        # response_model=ConversationResponse,
        summary="创建对话",
    )
    async def create_conversation(self):
        conversation =  await self.service.create_conversations(self.current_user.id)
        return ConversationResponse.model_validate(conversation)
    

    @router.post(
        "/{id}/messages",
        status_code=status.HTTP_200_OK,
        response_class=EventSourceResponse,
        summary="流式对话",
        dependencies=[Depends(verify)]
    )
    async def send_message(
        self,
        id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9]{12}$")],
        req: ConversationMessageRequest,
    ):
        async for chunk in self.service.send_message(req.message, id):
            yield ServerSentEvent(
                raw_data=json.dumps(chunk, ensure_ascii=False),
                event="message",
            )
        yield ServerSentEvent(raw_data="[DONE]", event="done")
