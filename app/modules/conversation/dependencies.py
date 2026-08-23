"""conversation 模块的 FastAPI 依赖：可被本模块及其它模块（如 itinerary）复用。"""
from typing import Annotated

from fastapi import Depends, Path

from app.shared.annotations import ConversationId
from app.shared.db.models import User
from app.modules.user.dependencies import get_current_user
from .service import ConversationService


async def require_conversation_owner(
    id: Annotated[ConversationId, Path()],
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ConversationService, Depends()],
):
    """校验当前用户是否拥有该对话（conversation 域的授权逻辑，供各处复用）。"""
    await service.check_authorization(user_id=user.id, conversation_id=id)