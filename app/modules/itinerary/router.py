from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute
from app.modules.user.dependencies import get_current_user
from app.shared.annotations import ConversationId
from app.modules.conversation.dependencies import verify_conversation_owner
from app.shared.db.models import User
from .service import ItineraryService

router = APIRouter(prefix="/itineraries", tags=["itineraries"], route_class=UnifiedRoute)


@cbv(router)
class ItineraryRouter:
    service: ItineraryService = Depends()
    current_user: User = Depends(get_current_user)

    @router.post(
        "/extract/{id}",
        status_code=status.HTTP_201_CREATED,
        summary="提取并保存结构化行程",
        dependencies=[Depends(verify_conversation_owner)],
    )
    async def extract_and_save_itinerary(
        self,
        id: Annotated[ConversationId, Path()],
    ):
        # 同步等待：LLM 提取 + 落库一次完成；失败抛业务异常由统一响应返回错误码。
        return await self.service.save_itinerary_from_conversation(id,self.current_user.id)