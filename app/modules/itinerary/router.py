from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute
from app.shared.annotations import ConversationId
from app.modules.user.dependencies import get_current_user
from app.shared.db.models import User
from .service import ItineraryService

router = APIRouter(prefix="/itineraries", tags=["itineraries"], route_class=UnifiedRoute)


async def verify(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ItineraryService, Depends()],
    id: Annotated[ConversationId, Path()],
):
    """校验当前用户是否拥有该对话的访问权限。"""
    await service.check_authorization(user_id=user.id, conversation_id=id)


@cbv(router)
class ItineraryRouter:
    service: ItineraryService = Depends()

    @router.post(
        "/extract/{id}",
        status_code=status.HTTP_201_CREATED,
        summary="提取并保存结构化行程",
        dependencies=[Depends(verify)],
    )
    async def extract_and_save_itinerary(
        self,
        id: Annotated[ConversationId, Path()],
    ):
        # 同步等待：LLM 提取 + 落库一次完成。
        # 成功返回行程数据；失败（如最后一条 AI 消息不含行程内容）抛业务异常，由统一响应返回错误码。
        return await self.service.save_itinerary_from_conversation(id)