import json
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute

from .schemas import (
    ConversationMessageRequest,
    ConversationResponse,
)
from .service import ConversationService

router = APIRouter(
    prefix="/conversations", tags=["conversation"], route_class=UnifiedRoute
)


@cbv(router)
class ConversationRouter:
    service: ConversationService = Depends()

    # ===================== TODO / 已知限制 =====================
    # 1. 鉴权与归属：目前无用户模块，所有 /{id} 端点只校验 id 格式(12位)，
    #    不校验“会话是否创建过/是否属于当前用户”。将来绑定 user_id 后需补：
    #    - create: 写 conversation 表(user_id, id, created_at)
    #    - read/update/delete: 先校验存在 + ownership
    # 2. 列表/分页：GET /conversations（按用户 id 拉全部）尚未实现；
    #    GET /{id}/messages 将来需支持 offset/limit 分批返回。
    # 3. 消息按轮次返回：从一条 HumanMessage → AI/Tool → 至下一条 HumanMessage 前的分组。
    # =============================================================

    @router.get(
        "/{id}/messages",
        status_code=status.HTTP_200_OK,
        summary="获取历史对话消息",
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
        return ConversationResponse()

    @router.post(
        "/{id}/messages",
        status_code=status.HTTP_200_OK,
        response_class=EventSourceResponse,
        summary="流式对话",
    )
    async def send_message(
        self,
        id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9]{12}$")],
        req: ConversationMessageRequest,
    ) -> AsyncIterable[ServerSentEvent]:
        async for chunk in self.service.send_message(req.message, id):
            yield ServerSentEvent(
                raw_data=json.dumps(chunk, ensure_ascii=False),
                event="message",
            )
        yield ServerSentEvent(raw_data="[DONE]", event="done")
