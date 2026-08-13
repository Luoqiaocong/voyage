import json

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from collections.abc import AsyncIterable
from app.modules.chat.service import ChatService
from app.modules.chat.schemas import ChatRequest

router = APIRouter(prefix="/chat", tags=["chat"])

@cbv(router)
class ChatRouter:
    service : ChatService = Depends()

    @router.post("/completions", status_code=status.HTTP_200_OK, response_class=EventSourceResponse)
    async def chat_endpoint(self, req: ChatRequest) -> AsyncIterable[ServerSentEvent]:
        """
        chat endpoint
        """
        async for text in self.service.process_message(req.message, req.session_id):
           yield ServerSentEvent(
        raw_data=json.dumps({"content": text}, ensure_ascii=False),
        event="token"
    )
        yield ServerSentEvent(raw_data="[DONE]", event="done")