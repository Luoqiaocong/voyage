from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute
from app.modules.conversation.dependencies import verify_conversation_owner
from app.modules.user.dependencies import get_current_user
from app.shared.annotations import ConversationId, ItineraryId
from app.shared.db.models import User

from .dependencies import verify_itinerary_owner
from .schemas import ItinerariesResponse, ItineraryDetailResponse, ItineraryPatch, UpdateItineraryRequest
from .service import ItineraryService

router = APIRouter(prefix="/itineraries", tags=["itineraries"], route_class=UnifiedRoute)


@cbv(router)
class ItineraryRouter:
    service: ItineraryService = Depends()
    current_user: User = Depends(get_current_user)

    # ---------- 生成 ----------
    @router.post(
        "/extract/{id}",
        status_code=status.HTTP_201_CREATED,
        summary="提取行程",
        dependencies=[Depends(verify_conversation_owner)],
    )
    async def extract_and_save_itinerary(
        self,
        id: Annotated[ConversationId, Path(description="对话 ID")],
    ):
        # 同步等待：LLM 提取 + 落库一次完成；失败抛业务异常由统一响应返回错误码。
        return ItineraryDetailResponse.model_validate(
            await self.service.save_from_conversation(id, self.current_user.id)
        )

    # ---------- 查询 ----------
    @router.get(
        "/",
        status_code=status.HTTP_200_OK,
        summary="获取行程列表",
    )
    async def get_itineraries(self):
        itineraries = await self.service.get_itineraries(self.current_user.id)
        return ItinerariesResponse(
            itineraries=[ItineraryDetailResponse.model_validate(i) for i in itineraries]
        )

    @router.get(
        "/{id}",
        status_code=status.HTTP_200_OK,
        summary="获取行程",
        dependencies=[Depends(verify_itinerary_owner)],
    )
    async def get_itinerary(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
    ):
        return ItineraryDetailResponse.model_validate(await self.service.get_itinerary(id))

    # ---------- 更新 ----------
    @router.put(
        "/{id}",
        status_code=status.HTTP_200_OK,
        summary="整体替换行程（前端整体编辑保存）",
        dependencies=[Depends(verify_itinerary_owner)],
    )
    async def update_itinerary(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
        update_req: UpdateItineraryRequest,
    ):
        # PUT = 整体替换：前端把整份行程编辑后全量保存（含未变的字段）。
        # 修改行程请到对话界面重新生成（带工具），旧行程可保留或删除。
        return ItineraryDetailResponse.model_validate(
            await self.service.update_itinerary(id, update_req.model_dump())
        )

    @router.patch(
        "/{id}",
        status_code=status.HTTP_200_OK,
        summary="局部更新行程独立字段（前端微调预算/偏好/交通/提醒/住宿）",
        dependencies=[Depends(verify_itinerary_owner)],
    )
    async def patch_itinerary(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
        patch_req: ItineraryPatch,
    ):
        # PATCH = 前端局部微调：只传要改的独立字段，派生字段不可在此修改（白名单）。
        # 未传字段保持不变；显式 null 视为不修改。
        return ItineraryDetailResponse.model_validate(
            await self.service.patch_itinerary(id, patch_req)
        )

    # ---------- 删除 ----------
    @router.delete(
        "/{id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="删除行程",
        dependencies=[Depends(verify_itinerary_owner)],
    )
    async def delete_itinerary(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
    ):
        await self.service.delete_itinerary(id)