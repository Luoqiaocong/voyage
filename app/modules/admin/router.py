"""管理端接口。

权限分两级：
  - 路由级依赖 get_current_admin —— **读取**权限，普通管理员与超管都可。
  - 写接口额外注入 get_current_super_admin —— **写入**权限，仅超管。

之所以在路由级就挂读权限（而不是逐个端点声明）：新增端点时天然受保护，
不会因遗漏而裸奔。写接口则必须显式换成超管依赖，这个「必须显式」是刻意的 ——
漏掉会直接表现为接口权限过宽，在测试(test_admin_roles)里能立刻发现。
"""
import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from fastapi_utils.cbv import cbv
from starlette import status

from app.config import config
from app.core.route import UnifiedRoute
from app.modules.user.constants import ROLE_SUPER_ADMIN
from app.modules.user.dependencies import get_current_admin, get_current_super_admin
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
    # 读取身份：普通管理员即可。
    #
    # ⚠️ 这里是 **类级依赖**，@cbv 会把它应用到本类**所有**路由。
    # 因此绝不能把「仅超管」的依赖也放在这一层 —— 那会让只读看板也要求超管，
    # 普通管理员就什么都看不到，与「只有查看权限」的定位完全相反。
    # 超管依赖只加在两个写端点的函数参数上（见 update_role / update_status）。
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
        role: Annotated[
            str | None, Query(description="按角色筛选：user / admin / super_admin")
        ] = None,
        is_active: Annotated[bool | None, Query(description="按启用状态筛选")] = None,
    ):
        """用户列表。

        结果里**不含层级高于当前查看者的账号** —— 普通管理员看不到超级管理员的
        邮箱（那是可被用于撞库或钓鱼的信息）。过滤在 SQL 层完成，
        因此 total 与分页也是一致的，不会出现「本页 10 条但总共说有 12 条」。
        """
        return await self.service.list_users(
            page=page,
            page_size=page_size,
            keyword=keyword,
            role=role,
            is_active=is_active,
            viewer_role=self.current_admin.role,
        )

    @router.get("/users/{user_id}", summary="用户详情", status_code=status.HTTP_200_OK)
    async def get_user(self, user_id: int):
        return await self.service.get_user_detail(user_id)

    @router.get("/me", summary="当前管理员的身份与权限", status_code=status.HTTP_200_OK)
    async def me(self):
        """前端据此决定是否渲染写操作按钮（改角色 / 停用）。

        另有许多接口在写操作时会被后端拒绝，但**前端提前隐藏**能避免用户
        点了才收到「权限不足」，那是更差的体验。
        """
        return {
            "id": self.current_admin.id,
            "email": self.current_admin.email,
            "username": self.current_admin.username,
            "role": self.current_admin.role,
            "can_write": self.current_admin.role == ROLE_SUPER_ADMIN,
        }

    @router.patch("/users/{user_id}/role", summary="修改用户角色（仅超级管理员）", status_code=status.HTTP_200_OK)
    async def update_role(
        self,
        user_id: int,
        req: RoleUpdateRequest,
        request: Request,
        # 超管权限在**函数参数**上声明，而不是类级依赖 ——
        # 类级依赖会作用于本类全部路由（见 current_admin 处的说明）。
        operator: User = Depends(get_current_super_admin),
    ):
        return await self.service.update_role(
            operator=operator,
            target_id=user_id,
            new_role=req.role,
            ip=_client_ip(request),
        )

    @router.patch("/users/{user_id}/status", summary="启用/禁用用户（仅超级管理员）", status_code=status.HTTP_200_OK)
    async def update_status(
        self,
        user_id: int,
        req: StatusUpdateRequest,
        request: Request,
        operator: User = Depends(get_current_super_admin),
    ):
        return await self.service.update_status(
            operator=operator,
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
