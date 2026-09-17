"""管理端接口：全部要求管理员身份（见 get_current_admin）。"""
import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from fastapi_utils.cbv import cbv
from starlette import status

from app.config import config
from app.core.route import UnifiedRoute
from app.modules.user.dependencies import get_current_admin
from app.shared.db.models import User

from .schemas import (
    RoleUpdateRequest,
    StatusUpdateRequest,
)
from .service import AdminService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    route_class=UnifiedRoute,
    # 路由级统一鉴权：/admin 下所有接口都必须通过管理员校验。
    # 放在这里而非逐个端点声明，新增端点时天然受保护，不会因遗漏而裸奔。
    dependencies=[Depends(get_current_admin)],
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _csv_stream(content: str, filename: str) -> StreamingResponse:
    """把 CSV 文本包成下载响应。

    带 UTF-8 BOM：否则 Excel 打开中文会乱码。
    """
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _new_csv() -> tuple[io.StringIO, "csv._writer"]:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    return buffer, csv.writer(buffer)


@cbv(router)
class AdminRouter:
    service: AdminService = Depends()
    current_admin: User = Depends(get_current_admin)

    # ==================== 看板 ====================
    @router.get("/dashboard/summary", summary="看板概览", status_code=status.HTTP_200_OK)
    async def dashboard_summary(self):
        return await self.service.dashboard_summary()

    @router.get("/dashboard/trend", summary="增长与消耗趋势", status_code=status.HTTP_200_OK)
    async def dashboard_trend(
        self,
        days: Annotated[int, Query(ge=1, le=90, description="统计天数")] = config.USAGE_DAYS_TREND_DEFAULT,
    ):
        return await self.service.dashboard_trend(days)

    @router.get("/dashboard/models", summary="模型用量分布与成本", status_code=status.HTTP_200_OK)
    async def dashboard_models(
        self,
        day: Annotated[str | None, Query(description="指定日期 yyyy-MM-dd；不传则统计全部历史")] = None,
    ):
        return await self.service.dashboard_models(day)

    @router.get("/dashboard/health", summary="系统健康检查", status_code=status.HTTP_200_OK)
    async def dashboard_health(self):
        return await self.service.dashboard_health()

    # ==================== 可观测性 ====================
    @router.get(
        "/metrics",
        summary="工具/提取/对话指标（命中率、通过率、延迟分位）",
        status_code=status.HTTP_200_OK,
    )
    async def metrics(
        self,
        day: Annotated[
            str | None, Query(description="指定日期 yyyy-MM-dd；不传则取今日")
        ] = None,
    ):
        return await self.service.metrics(day)

    @router.get(
        "/metrics/trend",
        summary="指标趋势（近 N 天）",
        status_code=status.HTTP_200_OK,
    )
    async def metrics_trend(
        self,
        days: Annotated[int, Query(ge=1, le=90, description="统计天数")] = config.USAGE_DAYS_TREND_DEFAULT,
    ):
        return await self.service.metrics_trend(days)

    # ==================== 用户管理 ====================
    @router.get("/users", summary="用户列表（分页/搜索/筛选）", status_code=status.HTTP_200_OK)
    async def list_users(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = config.ADMIN_PAGE_SIZE_DEFAULT,
        keyword: Annotated[str | None, Query(description="按邮箱或昵称模糊搜索")] = None,
        role: Annotated[str | None, Query(description="按角色筛选：user / admin")] = None,
        is_active: Annotated[bool | None, Query(description="按启用状态筛选")] = None,
    ):
        return await self.service.list_users(
            page=page, page_size=page_size, keyword=keyword, role=role, is_active=is_active
        )

    @router.get("/users/{user_id}", summary="用户详情", status_code=status.HTTP_200_OK)
    async def get_user(self, user_id: int):
        return await self.service.get_user_detail(user_id)

    @router.patch("/users/{user_id}/role", summary="修改用户角色", status_code=status.HTTP_200_OK)
    async def update_role(self, user_id: int, req: RoleUpdateRequest, request: Request):
        return await self.service.update_role(
            operator=self.current_admin, target_id=user_id, new_role=req.role, ip=_client_ip(request)
        )

    @router.patch("/users/{user_id}/status", summary="启用/禁用用户", status_code=status.HTTP_200_OK)
    async def update_status(self, user_id: int, req: StatusUpdateRequest, request: Request):
        return await self.service.update_status(
            operator=self.current_admin,
            target_id=user_id,
            is_active=req.is_active,
            ip=_client_ip(request),
        )

    # ==================== 会话洞察 ====================
    @router.get("/conversations/stats", summary="会话统计", status_code=status.HTTP_200_OK)
    async def conversation_stats(self):
        return await self.service.conversation_stats()

    @router.get(
        "/conversations",
        summary="会话元数据列表（不含任何用户内容）",
        status_code=status.HTTP_200_OK,
    )
    async def list_conversations(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = config.ADMIN_PAGE_SIZE_DEFAULT,
        user_id: Annotated[int | None, Query(description="按用户筛选")] = None,
        sort: Annotated[
            str,
            Query(
                pattern="^(created_desc|messages_desc)$",
                description="created_desc=最新创建在前；messages_desc=消息数从多到少",
            ),
        ] = "created_desc",
    ):
        """只返回会话的**元数据**：id、所属用户、消息数、创建时间。

        隐私约束（重要）：
        - 不返回会话标题。标题由 LLM 从用户消息生成，属于用户内容，
          对管理员可见即构成内容层面的隐私泄露。
        - 不提供 keyword 检索。原先按标题模糊搜索，等于允许对全站用户的
          对话标题做关键词检索，是系统性的窥探能力，已移除。
        运营所需的规模与活跃度信息由 /conversations/stats 的聚合数据满足。
        """
        return await self.service.list_conversations(
            page=page, page_size=page_size, user_id=user_id, sort=sort
        )

    # ==================== 审计日志 ====================
    @router.get("/audit-logs", summary="管理操作审计日志", status_code=status.HTTP_200_OK)
    async def list_audit_logs(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = config.ADMIN_PAGE_SIZE_DEFAULT,
        action: Annotated[str | None, Query(description="按动作标识筛选")] = None,
        operator_id: Annotated[int | None, Query(description="按操作者筛选")] = None,
        target_id: Annotated[str | None, Query(description="按目标对象筛选")] = None,
    ):
        return await self.service.list_audit_logs(
            page=page,
            page_size=page_size,
            action=action,
            operator_id=operator_id,
            target_id=target_id,
        )

    # ==================== 导出 ====================
    @router.get("/export/users.csv", summary="导出用户列表 CSV")
    async def export_users(self) -> StreamingResponse:
        buffer, writer = _new_csv()
        writer.writerow(["id", "email", "username", "role", "is_active", "created_at"])
        async for row in self.service.repo.iter_users_for_export():
            writer.writerow([row[0], row[1], row[2], row[3], row[4], row[5]])
        return _csv_stream(buffer.getvalue(), "users.csv")

    @router.get("/export/token-usage.csv", summary="导出 Token 用量 CSV")
    async def export_token_usage(self) -> StreamingResponse:
        buffer, writer = _new_csv()
        writer.writerow(
            ["record_date", "model", "input_tokens", "output_tokens", "total_tokens", "calls"]
        )
        async for row in self.service.repo.iter_token_usage_for_export():
            writer.writerow([row[0], row[1], row[2], row[3], row[4], row[5]])
        return _csv_stream(buffer.getvalue(), "token-usage.csv")
