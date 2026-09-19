"""行程分享与导出接口。

两组端点的鉴权模型截然不同，故分成两个 router：
- owner_router：/itineraries/... 下，需登录 + 行程归属校验（管理自己的分享）。
- public_router：/share/... 下，**不需要登录**——这正是分享的意义。
  安全性由令牌 + 可选密码保证，而非登录态；因此这里必须格外注意
  只暴露必要信息、不泄露行程 ID 之外的内容。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from fastapi.responses import PlainTextResponse
from fastapi_utils.cbv import cbv
from starlette import status

from app.config import config
from app.core.route import UnifiedRoute
from app.modules.user.dependencies import get_current_user
from app.shared.annotations import ItineraryId
from app.shared.db.models import User

from .exporters import build_ics, build_markdown, build_printable_html
from .schemas import ItineraryPlan
from .share_schemas import (
    CopySharedRequest,
    CreateShareRequest,
    ExtendSharedRequest,
    ShareCheckResponse,
    SharedItineraryResponse,
    ShareItem,
    ShareListResponse,
)
from .share_service import ShareService

# ==================== 分享者侧（需登录） ====================
owner_router = APIRouter(prefix="/itineraries", tags=["itinerary-shares"], route_class=UnifiedRoute)

# ==================== 访问者侧（公开） ====================
public_router = APIRouter(prefix="/share", tags=["share-public"], route_class=UnifiedRoute)


def _share_url(token: str) -> str:
    """拼出可复制的完整分享链接。"""
    return f"{config.SHARE_BASE_URL.rstrip('/')}/share/{token}"


def _share_item(share) -> ShareItem:
    status_ = ShareService._status_of(share)
    return ShareItem(
        id=share.id,
        itinerary_id=share.itinerary_id,
        token=share.token,
        url=_share_url(share.token),
        allow_copy=share.allow_copy,
        allow_edit=share.allow_edit,
        has_password=bool(share.password_hash),
        password=share.password_plain,
        expires_at=share.expires_at,
        revoked_at=share.revoked_at,
        view_count=share.view_count or 0,
        created_at=share.created_at,
        status=status_,
    )


@cbv(owner_router)
class ShareOwnerRouter:
    service: ShareService = Depends()
    current_user: User = Depends(get_current_user)

    @owner_router.post(
        "/{id}/shares",
        status_code=status.HTTP_201_CREATED,
        summary="创建行程分享链接",
    )
    async def create_share(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
        req: CreateShareRequest,
    ):
        share = await self.service.create_share(
            user_id=self.current_user.id,
            itinerary_id=id,
            allow_copy=req.allow_copy,
            allow_edit=req.allow_edit,
            password=req.password,
            expires_in_days=req.expires_in_days,
        )
        return _share_item(share)

    @owner_router.get(
        "/{id}/shares",
        status_code=status.HTTP_200_OK,
        summary="查看某行程的全部分享链接",
    )
    async def list_shares(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
    ):
        shares = await self.service.list_shares(user_id=self.current_user.id, itinerary_id=id)
        return ShareListResponse(shares=[_share_item(s) for s in shares])

    @owner_router.patch(
        "/shares/{share_id}",
        status_code=status.HTTP_200_OK,
        summary="修改分享设置（权限/密码/有效期）",
    )
    async def update_share(
        self,
        share_id: Annotated[int, Path(ge=1, description="分享 ID")],
        req: CreateShareRequest,
        clear_password: Annotated[bool, Query(description="设为 true 则清除访问密码")] = False,
        clear_expiry: Annotated[bool, Query(description="设为 true 则改为永不过期")] = False,
    ):
        """修改分享设置，**只改请求里显式给出的字段**。

        这里必须用 model_fields_set 过滤，不能直接把 req.allow_copy 传下去：
        CreateShareRequest 的 allow_copy 有默认值 True，Pydantic 会把未传的
        字段填成默认值，于是 service 里 `if allow_copy is not None` 恒为真，
        「只改传入字段」的意图落空。

        实测后果：用户先关掉「允许复制」，之后只想关「允许编辑」而只传
        allow_edit 时，allow_copy 会被静默还原为默认的 True —— 用户会以为
        权限设置不稳定。故未显式传入的一律按 None 传递，让 service 跳过。
        """
        given = req.model_fields_set
        share = await self.service.update_share(
            user_id=self.current_user.id,
            share_id=share_id,
            allow_copy=req.allow_copy if "allow_copy" in given else None,
            allow_edit=req.allow_edit if "allow_edit" in given else None,
            password=req.password if "password" in given else None,
            clear_password=clear_password,
            expires_in_days=req.expires_in_days if "expires_in_days" in given else None,
            clear_expiry=clear_expiry,
        )
        return _share_item(share)

    @owner_router.delete(
        "/shares/{share_id}",
        status_code=status.HTTP_200_OK,
        summary="删除分享链接",
    )
    async def revoke_share(
        self,
        share_id: Annotated[int, Path(ge=1, description="分享 ID")],
    ):
        """删除分享链接（物理删除）。

        返回 {id, deleted: true} 而不是被删对象：
        记录已不存在，序列化一个已删除的实体没有意义，
        也无法区分「删除成功」与「对象还在」。
        """
        await self.service.revoke_share(user_id=self.current_user.id, share_id=share_id)
        return {"id": share_id, "deleted": True}


@cbv(public_router)
class SharePublicRouter:
    service: ShareService = Depends()

    @public_router.get(
        "/{token}",
        status_code=status.HTTP_200_OK,
        summary="预检分享链接（是否可用、是否需要密码）",
    )
    async def inspect(self, token: Annotated[str, Path(min_length=16, max_length=64)]):
        return ShareCheckResponse(**await self.service.inspect(token))

    @public_router.get(
        "/{token}/itinerary",
        status_code=status.HTTP_200_OK,
        summary="通过分享链接读取行程",
    )
    async def open_shared(
        self,
        token: Annotated[str, Path(min_length=16, max_length=64)],
        password: Annotated[
            str | None, Header(alias="X-Share-Password", description="访问密码（若分享设置了密码）")
        ] = None,
        pwd: Annotated[
            str | None, Query(description="访问密码（查询参数形式，便于浏览器直接打开）")
        ] = None,
    ):
        # 同时支持请求头与查询参数：前者适合前端调用，后者便于用户在浏览器里带密码访问
        payload, _share = await self.service.open_shared(token=token, password=password or pwd)
        return SharedItineraryResponse(**payload)

    @public_router.post(
        "/{token}/copy",
        status_code=status.HTTP_201_CREATED,
        summary="把分享的行程复制到自己的账号（需登录）",
    )
    async def copy_shared(
        self,
        token: Annotated[str, Path(min_length=16, max_length=64)],
        req: CopySharedRequest,
        current_user: Annotated[User, Depends(get_current_user)],
        password: Annotated[str | None, Header(alias="X-Share-Password")] = None,
        pwd: Annotated[str | None, Query(description="访问密码")] = None,
    ):
        itinerary = await self.service.copy_to_my_account(
            token=token, password=password or pwd, user_id=current_user.id
        )
        return {"id": itinerary.id, "plan": itinerary.plan}

    @public_router.patch(
        "/{token}/itinerary",
        status_code=status.HTTP_200_OK,
        summary="在分享链接上编辑行程（需分享开启 allow_edit）",
    )
    async def extend_shared(
        self,
        token: Annotated[str, Path(min_length=16, max_length=64)],
        req: ExtendSharedRequest,
        password: Annotated[str | None, Header(alias="X-Share-Password")] = None,
        pwd: Annotated[str | None, Query(description="访问密码")] = None,
        authorization: Annotated[str | None, Header()] = None,
    ):
        # 编辑人身份是可选的：登录了就带上（所有者本人编辑会写回原件），
        # 未登录也能拿到合并结果但要自行保存。
        user_id: int | None = None
        if authorization and authorization.lower().startswith("bearer "):
            user_id = await _optional_user_id(authorization.split(" ", 1)[1])

        is_applied, plan = await self.service.extend_shared(
            token=token,
            password=password or pwd,
            user_id=user_id,
            changes=req.model_dump(exclude_unset=True),
        )
        return {"is_applied": is_applied, "plan": plan}


async def _optional_user_id(token: str) -> int | None:
    """尽力解析登录态：令牌无效时不报错，仅视为未登录。

    分享页是公开入口，不应因为带了过期令牌就整体失败——降级为匿名访问更合理。
    """
    try:
        from app.modules.auth.tokens import decode_access_token
        from app.modules.user.auth import get_real_id

        payload = decode_access_token(token)
        sub = payload.get("sub")
        return get_real_id(str(sub)) if sub else None
    except Exception:  # noqa: BLE001 - 分享页容错优先
        return None


# ==================== 导出（需登录 + 行程归属） ====================
export_router = APIRouter(prefix="/itineraries", tags=["itinerary-export"], route_class=UnifiedRoute)


@cbv(export_router)
class ItineraryExportRouter:
    service: ShareService = Depends()
    current_user: User = Depends(get_current_user)

    @export_router.get("/{id}/export/calendar.ics", summary="导出为日历文件（可导入手机日历）")
    async def export_ics(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
    ) -> Response:
        await self.service.check_own_itinerary(self.current_user.id, id)
        itinerary = await self.service.itinerary_repo.get(id)
        plan = ItineraryPlan.model_validate(itinerary.plan)
        content = build_ics(plan, itinerary_id=id)
        return Response(
            content=content.encode("utf-8"),
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="itinerary-{id}.ics"'
                )
            },
        )

    @export_router.get("/{id}/export/markdown", summary="导出为 Markdown")
    async def export_markdown(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
    ) -> Response:
        await self.service.check_own_itinerary(self.current_user.id, id)
        itinerary = await self.service.itinerary_repo.get(id)
        plan = ItineraryPlan.model_validate(itinerary.plan)
        return PlainTextResponse(
            build_markdown(plan, itinerary_id=id),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="itinerary-{id}.md"'},
        )

    @export_router.get(
        "/{id}/export/print", summary="导出打印友好 HTML（浏览器可另存为 PDF）"
    )
    async def export_printable(
        self,
        id: Annotated[ItineraryId, Path(ge=1, description="行程 ID")],
    ) -> Response:
        await self.service.check_own_itinerary(self.current_user.id, id)
        itinerary = await self.service.itinerary_repo.get(id)
        plan = ItineraryPlan.model_validate(itinerary.plan)
        return Response(
            content=build_printable_html(plan, itinerary_id=id).encode("utf-8"),
            media_type="text/html; charset=utf-8",
        )
