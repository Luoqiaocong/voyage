import json
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
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


"""
TODO:
    1.根据某个用户uid获取所有对话历史
"""


@cbv(router)
class ConversationRouter:
    service: ConversationService = Depends()

    """
    TODO：未来不能一次性返回全部对话，要分批，按轮次返回（
    从一条 HumanMessage 开始
    → 后面的 AI / Tool / AI ...
    → 直到下一条 HumanMessage 之前
    ）
    """

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
    
    """
    TODO： 以后要验证用户是否有权限访问此会话id，会话id是否存在
    """
    
    @router.delete(
         "/{id}/messages",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="删除历史对话消息",
    )
    async def delete_messages(
        self,
        id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9]{12}$")],
    ):
       return await self.service.delete_messages(id)

    """
    TODO:
    后续必须携带鉴权，以标识是用户；认证后创建 conversation，
    但不对 conversation 作存储，只在后续有对话时进行存储
    """

    @router.post(
        "/",
        status_code=status.HTTP_201_CREATED,
        # response_model=ConversationResponse,
        summary="创建对话",
    )
    async def create_conversation(self):
        return ConversationResponse()

    """
    """

    @router.post(
        "/{id}/messages",
        status_code=status.HTTP_200_OK,
        response_class=EventSourceResponse,
        summary="流式对话",
    )
    async def chat(
        self,
        id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9]{12}$")],
        req: ConversationMessageRequest,
    ) -> AsyncIterable[ServerSentEvent]:
        async for chunk in self.service.process_message(req.message, id):
            yield ServerSentEvent(
                raw_data=json.dumps(chunk, ensure_ascii=False),
                event="message",
            )
        yield ServerSentEvent(raw_data="[DONE]", event="done")
