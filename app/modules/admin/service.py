"""管理端业务层。

设计要点
--------
1. 所有写操作都写审计日志，且与业务变更在同一事务内——
   保证「改了」与「留痕」要么都生效、要么都不生效。
2. 两条自我保护规则，避免管理员把系统管死：
   - 不能停用自己（否则可能把自己锁在门外）；
   - 不能停用/降级最后一个启用状态的管理员（否则后台再无人可进）。
3. 看板查询前会先 flush 一次 Redis 增量，保证「今日消耗」不偏小。

注意：本模块**不要**加 `from __future__ import annotations`。
那会把 __init__ 的注解变成字符串，FastAPI 依赖注入无法解析
（表现为 Invalid args for response field），项目其余 service 亦无此行。
"""
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.core.business import BusinessCode, UserException
from app.modules.user.constants import (
    ROLE_SUPER_ADMIN,
    VALID_ROLES,
    can_manage_role,
    role_rank,
)
from app.shared import audit
from app.shared.db import get_db
from app.shared.db.models import User
from app.shared.redis import redis_client
from app.shared.usage_query import (
    estimate_cost_usd,
    get_model_breakdown,
    get_platform_counters,
    get_token_summary,
    get_token_trend,
    get_user_growth_trend,
    local_today,
)
from app.shared.usage_store import flush_pending_usage
from app.shared.utils import TransactionMixin, log, to_local_display

from .repo import AdminRepo


class AdminService(TransactionMixin):
    def __init__(
        self,
        repo: Annotated[AdminRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> None:
        self.repo = repo
        self.db = db

    # ==================== 看板 ====================
    async def dashboard_summary(self) -> dict[str, Any]:
        """看板概览。

        先 flush Redis 增量再聚合：否则「今日消耗」只反映上一次落库的快照，
        用户会看到一个比真实值偏小的数字。
        """
        try:
            await flush_pending_usage()
        except Exception:
            # 落库失败不应阻断看板展示，退化为「读取已落库部分」
            log.exception("[admin] 看板前的用量落库失败，改用已落库数据")

        token = await get_token_summary(self.db, local_today())
        counters = await get_platform_counters(self.db)
        breakdown = await get_model_breakdown(self.db, local_today())

        return {
            "today": token["date"],
            "today_tokens": token["total_tokens"],
            "today_calls": token["calls"],
            "new_users_today": counters["new_users_today"],
            "active_users_today": counters["active_users_today"],
            "total_users": counters["total_users"],
            "total_conversations": counters["total_conversations"],
            "total_itineraries": counters["total_itineraries"],
            "today_cost": estimate_cost_usd(breakdown),
        }

    async def dashboard_trend(self, days: int) -> dict[str, Any]:
        """用户增长与 Token 消耗趋势（同图对齐，便于前端合并展示）。"""
        days = max(1, min(days, config.USAGE_DAYS_TREND_MAX))
        return {
            "days": days,
            "users": await get_user_growth_trend(self.db, days),
            "tokens": await get_token_trend(self.db, days),
        }

    async def dashboard_models(self, day: str | None = None) -> dict[str, Any]:
        """模型用量分布与成本估算。day 为空时统计全部历史。"""
        await self._safe_flush()
        breakdown = await get_model_breakdown(self.db, day)
        total = sum(item["total_tokens"] for item in breakdown)
        for item in breakdown:
            item["share"] = round(item["total_tokens"] / total, 4) if total else 0.0
        return {
            "scope": day or "all",
            "breakdown": breakdown,
            "cost": estimate_cost_usd(breakdown),
        }

    async def dashboard_health(self) -> dict[str, Any]:
        """系统健康检查。

        刻意**不**对 LLM 通道发起真实调用：那会消耗额度。只校验配置是否完整，
        真正的通道可用性由实际对话请求自然暴露（失败会写日志）。
        """
        redis_ok, redis_detail = False, ""
        try:
            client = redis_client.get_client()
            await client.ping()
            info = await client.info("server")
            redis_ok = True
            redis_detail = f"Redis {info.get('redis_version', 'unknown')}"
        except Exception as exc:  # noqa: BLE001
            redis_detail = f"{type(exc).__name__}: {str(exc)[:120]}"

        db_ok, db_detail = False, ""
        try:
            from sqlalchemy import text

            await self.db.execute(text("select 1"))
            db_ok = True
            # 从引擎实际连接的方言取名，而不是写死。
            # 写死过 "SQLite 连接正常"，切到 PostgreSQL 后仍在报 SQLite，
            # 属于会误导运维的错误信息。
            db_detail = f"{self.db.bind.dialect.name} 连接正常"
        except Exception as exc:  # noqa: BLE001
            db_detail = f"{type(exc).__name__}: {str(exc)[:120]}"

        configured = bool(config.OPENCODE_GO_URL and config.OPENCODE_API_KEY)

        return {
            "redis_ok": redis_ok,
            "redis_detail": redis_detail,
            "database_ok": db_ok,
            "database_detail": db_detail,
            "llm_channel_configured": configured,
            "llm_model": config.OPENCODE_LLM_MODEL,
            "llm_detail": (
                "配置完整（未实际发起调用以免消耗额度）" if configured else "缺少 URL 或 API Key"
            ),
        }

    async def _safe_flush(self) -> None:
        try:
            await flush_pending_usage()
        except Exception:
            log.exception("[admin] 用量落库失败，改用已落库数据")

    # ==================== 可观测性（第 4 期）====================
    async def metrics(self, day: str | None = None) -> dict[str, Any]:
        """读取某日的工具/提取/对话指标（含缓存命中率、延迟分位）。

        这些数字来自运行时埋点，是「优化到底有没有效」的判据：
        例如调整提示词后，extraction.pass_rate 是否上升；
        接入缓存后，cache.hit_rate 与工具延迟分位是否下降。
        """
        from app.shared.observability import get_metrics

        return await get_metrics(day)

    async def metrics_trend(self, days: int) -> dict[str, Any]:
        """近 N 天的指标趋势，供管理端画图。"""
        from app.config import config as _config
        from app.shared.observability import get_metrics_trend

        days = max(1, min(days, _config.USAGE_DAYS_TREND_MAX))
        return {"days": days, "trend": await get_metrics_trend(days)}

    # ==================== 用户管理 ====================
    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        viewer_role: str | None = None,
    ) -> dict[str, Any]:
        """用户列表。

        viewer_role：查看者的角色。据此**隐藏层级高于自己的账号** ——
        普通管理员在列表里看不到超级管理员，避免暴露其邮箱
        （可被用于撞库、钓鱼或针对性社工）。超级管理员能看到全部。
        """
        page = max(1, page)
        page_size = max(1, min(page_size, config.ADMIN_PAGE_SIZE_MAX))
        users, total = await self.repo.list_users(
            page=page,
            page_size=page_size,
            keyword=keyword,
            role=role,
            is_active=is_active,
            viewer_rank=role_rank(viewer_role) if viewer_role else None,
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            # 前端据此决定是否渲染「改角色 / 停用」等按钮，与后端权限保持一致
            "can_write": viewer_role == ROLE_SUPER_ADMIN,
            "items": [
                {
                    "id": u.id,
                    "email": u.email,
                    "username": u.username,
                    "avatar": u.avatar,
                    "role": u.role,
                    "is_active": u.is_active,
                    # 时间必须在此转换。
                    #
                    # 管理端**所有路由都没有声明 response_model**（虽然
                    # schemas.py 里定义了 AdminUserItem/AdminUserPage，但从未
                    # 被引用），因此 Pydantic 的 field_serializer **不会执行** ——
                    # 在 schema 上加序列化器完全不生效。
                    # 这也是「改了 schema 却没有任何变化」的原因。
                    # 统一在构造 dict 时转成本地时区字符串，与会话/行程模块一致。
                    "created_at": to_local_display(u.created_at) if u.created_at else None,
                }
                for u in users
            ],
        }

    async def get_user_detail(self, user_id: int) -> dict[str, Any]:
        user = await self._require_user(user_id)
        conversations, itineraries = await self.repo.user_usage_counts(user_id)
        return {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "avatar": user.avatar,
            "role": user.role,
            "is_active": user.is_active,
            # 同 list_users：路由未声明 response_model，schema 的序列化器不生效，
            # 时间必须在这里转（否则详情页显示 UTC，比实际早 8 小时）
            "created_at": to_local_display(user.created_at) if user.created_at else None,
            "conversation_count": conversations,
            "itinerary_count": itineraries,
        }

    async def update_role(
        self, *, operator: User, target_id: int, new_role: str, ip: str | None
    ) -> dict[str, Any]:
        """修改用户角色。仅超级管理员可达（路由层已用 get_current_super_admin 拦截）。"""
        if new_role not in VALID_ROLES:
            raise UserException(code=BusinessCode.PARAM_INVALID)

        target = await self._require_user(target_id)
        old_role = target.role
        if old_role == new_role:
            return {"id": target.id, "role": target.role, "changed": False}

        # 层级校验：只能管理级别严格低于自己的账号。
        # 这条同时挡住两件事——
        #   1. 普通管理员改动任何人（它的层级不高于绝大多数目标）
        #   2. 超级管理员互相降级（平级不能操作，避免内耗导致无人可管）
        if not can_manage_role(operator.role, target.role):
            raise UserException(
                code=BusinessCode.FORBIDDEN,
                msg="不能修改与自己同级或级别更高的账号",
            )
        # 提升他人时，新角色也不能达到或超过自己 —— 否则等于批量制造平级，
        # 甚至（若校验只看旧角色）可以造出比自己更高的账号。
        if not can_manage_role(operator.role, new_role):
            raise UserException(
                code=BusinessCode.FORBIDDEN,
                msg="不能把他人提升到与自己同级或更高的角色",
            )

        # 自我保护：不允许把自己降级。
        # 与「不能操作平级」是两条不同的理由——这里防的是误操作：
        # 一次不小心的点击就会让自己失去后台权限，且改回来需要别人帮忙。
        if target.id == operator.id:
            raise UserException(
                code=BusinessCode.FORBIDDEN,
                msg="不能修改自己的角色，请让其他超级管理员操作",
            )

        # 兜底：不允许平台失去最后一个启用的超级管理员。
        # 层级校验已能挡住大部分情况（超管之间互不可动），但若将来放开
        # 平级操作，这条是最后一道防线。
        if old_role == ROLE_SUPER_ADMIN and new_role != ROLE_SUPER_ADMIN:
            await self._ensure_not_last_super_admin(target.id, "降级")

        async with self.transaction_scope():
            target.role = new_role
            await self.db.flush()
            await audit.record(
                self.db,
                operator_id=operator.id,
                operator_email=operator.email,
                action="user.role.update",
                target_type="user",
                target_id=target.id,
                detail={"before": old_role, "after": new_role},
                ip=ip,
            )
        log.info(f"[admin] {operator.email} 将用户 {target.id} 角色 {old_role} -> {new_role}")
        return {"id": target.id, "role": target.role, "changed": True}

    async def update_status(
        self, *, operator: User, target_id: int, is_active: bool, ip: str | None
    ) -> dict[str, Any]:
        """启用/禁用用户。仅超级管理员可达（路由层已拦截）。"""
        target = await self._require_user(target_id)
        old = target.is_active
        if old == is_active:
            return {"id": target.id, "is_active": target.is_active, "changed": False}

        # 自我保护一：不能停用自己
        if not is_active and target.id == operator.id:
            raise UserException(
                code=BusinessCode.FORBIDDEN, msg="不能停用当前登录的管理员账号"
            )
        # 层级校验：只能管理级别严格低于自己的账号（含「普通管理员停用超管」）
        if not can_manage_role(operator.role, target.role):
            raise UserException(
                code=BusinessCode.FORBIDDEN,
                msg="不能操作与自己同级或级别更高的账号",
            )
        # 兜底：不能停用最后一个启用的超级管理员
        if not is_active and target.role == ROLE_SUPER_ADMIN:
            await self._ensure_not_last_super_admin(target.id, "停用")

        async with self.transaction_scope():
            target.is_active = is_active
            await self.db.flush()
            await audit.record(
                self.db,
                operator_id=operator.id,
                operator_email=operator.email,
                action="user.status.update",
                target_type="user",
                target_id=target.id,
                detail={"before": old, "after": is_active},
                ip=ip,
            )
        log.info(f"[admin] {operator.email} 将用户 {target.id} 启用状态 {old} -> {is_active}")
        return {"id": target.id, "is_active": target.is_active, "changed": True}

    async def _require_user(self, user_id: int) -> User:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise UserException(code=BusinessCode.USER_NOT_FOUND)
        return user

    async def _ensure_not_last_super_admin(self, target_id: int, action: str) -> None:
        """确保该操作不会让平台失去最后一个启用的超级管理员。

        注意统计的是 **super_admin** 而非 admin：普通管理员没有管理能力，
        即使还剩好几个也不能靠它们恢复权限。
        """
        supers = await self.repo.count_super_admins()
        target = await self.repo.get_user(target_id)
        target_is_active_super = (
            target is not None
            and target.role == ROLE_SUPER_ADMIN
            and target.is_active
        )
        if target_is_active_super and supers <= 1:
            raise UserException(
                code=BusinessCode.FORBIDDEN,
                msg=f"不能{action}最后一个启用状态的超级管理员，否则将无人可管理后台",
            )

    # ==================== 会话洞察 ====================
    async def conversation_stats(self) -> dict[str, Any]:
        stats = await self.repo.conversation_stats()
        # Token 排行放在同一份响应里返回：它与会话活跃排行同属「用户排行」，
        # 前端在一个卡片里用下拉切换口径，分成两个接口会多一次请求。
        #
        # 但要注意：**排行切换时不需要重新请求** —— 会话数 / 当日消息数
        # 两种口径都在 top_active_users 里；token 是另一种「量」，
        # 字段结构不同（tokens/calls），故单独一个数组。
        stats["top_token_users"] = await self.repo.top_token_users()
        return stats

    async def list_conversations(
        self, *, page: int, page_size: int, user_id: int | None = None, sort: str = "created_desc"
    ) -> dict[str, Any]:
        """会话元数据分页。

        不再接受 keyword：原先它按会话标题模糊搜索，
        等于给了管理员「对全站用户对话标题做关键词检索」的能力。
        标题本身也已不返回（见 repo.list_conversations 的隐私说明）。
        """
        page = max(1, page)
        page_size = max(1, min(page_size, config.ADMIN_PAGE_SIZE_MAX))
        items, total = await self.repo.list_conversations(
            page=page, page_size=page_size, user_id=user_id, sort=sort
        )
        return {"total": total, "page": page, "page_size": page_size, "items": items}

    # ==================== 审计日志 ====================
    async def list_audit_logs(
        self,
        *,
        page: int,
        page_size: int,
        action: str | None = None,
        operator_id: int | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(page_size, config.ADMIN_PAGE_SIZE_MAX))
        rows, total = await audit.list_logs(
            self.db,
            page=page,
            page_size=page_size,
            action=action,
            operator_id=operator_id,
            target_id=target_id,
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": r.id,
                    "operator_id": r.operator_id,
                    "operator_email": r.operator_email,
                    "action": r.action,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "detail": r.detail,
                    "ip": r.ip,
                    # 这里手工构造 dict、router 直接返回，**不经过 Pydantic schema**，
                    # 所以 schema 上的 field_serializer 不会生效 —— 必须在此显式转换。
                    # 否则下发的是原始 UTC，前端展示会早 8 小时。
                    "created_at": to_local_display(r.created_at) if r.created_at else None,
                }
                for r in rows
            ],
        }
