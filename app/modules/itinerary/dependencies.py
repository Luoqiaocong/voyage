"""itinerary 模块的 FastAPI 依赖：行程归属鉴权，供本模块路由复用。"""
from typing import Annotated

from fastapi import Depends, Path

from app.shared.annotations import ItineraryId
from app.shared.db.models import User
from app.modules.user.dependencies import get_current_user
from .service import ItineraryService


async def verify_itinerary_owner(
    id: Annotated[ItineraryId, Path()],
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ItineraryService, Depends()],
):
    """校验行程存在且属于当前用户（itinerary 域的授权逻辑，供各处复用）。"""
    await service.check_authorization(user_id=user.id, itinerary_id=id)