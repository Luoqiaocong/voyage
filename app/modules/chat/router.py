from fastapi import APIRouter
from app.modules.chat.service import chat_service
from app.modules.chat.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    reply, session_id = await chat_service.process_message(req.message, req.session_id)
    return ChatResponse(reply=reply, session_id=session_id)