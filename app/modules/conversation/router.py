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


@cbv(router)
class ConversationRouter:
    service: ConversationService = Depends()

    """
    未来不能一次性返回全部对话，要分批，所有有 skip，limit，pageSize 等参数（查询参数）
    """

    @router.get(
        "/{id}/messages",
        status_code=status.HTTP_200_OK,
        summary="获取对话历史消息",
    )
    async def get_messages(
        self,
        # start: Annotated[int, Query(ge=1, description="页码", alias="page")] = 1,
        # end: Annotated[int, Query(ge=1, le=50, description="每页数量", alias="pagesize")] = 10,
       id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9]{12}$")],
    ):
        return await self.service.get_messages(id)

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
