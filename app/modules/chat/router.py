import json

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from collections.abc import AsyncIterable
from .service import ChatService
from .schemas import ChatRequest, SessionResponse,SessionRequest
from app.core.route import UnifiedRoute

router = APIRouter(prefix="/chat", tags=["chat"],route_class=UnifiedRoute)

@cbv(router)
class ChatRouter:
    service : ChatService = Depends()
    
    @router.get("/sessions/{session_id}", 
                status_code=status.HTTP_200_OK,
                summary="获取会话")
    async def get_sessions(self,sess_req:SessionRequest=Depends()):
        return {"session_id":sess_req.session_id,"messages": [{"assistant": "AI", "content": "hello,how can I help you today?"}]}
    
    
    """
    TODO:
    后续必须携带鉴权，以标识是用户；认证后创建session，
    但不对session作存储，只在后续有对话时进行存储
    """
    @router.post("/sessions", 
                 status_code=status.HTTP_201_CREATED,
                #  response_model=SessionResponse,
                 summary="创建会话"
                 )  
    async def create_session(self):
        return SessionResponse()

    """
    #TODO:
    后续还有工具调用的流式返回   
    """
    @router.post("/completions", 
                 status_code=status.HTTP_200_OK,
                 response_class=EventSourceResponse,
                 summary="流式对话"
                 )
    async def chat_endpoint(self, req: ChatRequest) -> AsyncIterable[ServerSentEvent]:
        async for text in self.service.process_message(req.message, req.session_id):
           yield ServerSentEvent(
        raw_data=json.dumps({"content": text}, ensure_ascii=False),
        event="token"
    )
        yield ServerSentEvent(raw_data="[DONE]", event="done")