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
from app.modules.user.constants import ROLE_ADMIN, VALID_ROLES
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
from app.shared.utils import TransactionMixin, log

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
            db_detail = "SQLite 连接正常"
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
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(page_size, config.ADMIN_PAGE_SIZE_MAX))
        users, total = await self.repo.list_users(
            page=page,
            page_size=page_size,
            keyword=keyword,
            role=role,
            is_active=is_active,
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": u.id,
                    "email": u.email,
                    "username": u.username,
                    "avatar": u.avatar,
                    "role": u.role,
                    "is_active": u.is_active,
                    "created_at": u.created_at,
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
            "created_at": user.created_at,
            "conversation_count": conversations,
            "itinerary_count": itineraries,
        }

    async def update_role(
        self, *, operator: User, target_id: int, new_role: str, ip: str | None
    ) -> dict[str, Any]:
        """修改用户角色。"""
        if new_role not in VALID_ROLES:
            raise UserException(code=BusinessCode.PARAM_INVALID)

        target = await self._require_user(target_id)
        old_role = target.role
        if old_role == new_role:
            return {"id": target.id, "role": target.role, "changed": False}

        # 自我保护：不允许把最后一个启用状态的管理员降级
        if old_role == ROLE_ADMIN and new_role != ROLE_ADMIN:
            await self._ensure_not_last_admin(target.id, "降级")

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
        """启用/禁用用户。"""
        target = await self._require_user(target_id)
        old = target.is_active
        if old == is_active:
            return {"id": target.id, "is_active": target.is_active, "changed": False}

        # 自我保护一：不能停用自己
        if not is_active and target.id == operator.id:
            raise UserException(
                code=BusinessCode.FORBIDDEN, msg="不能停用当前登录的管理员账号"
            )
        # 自我保护二：不能停用最后一个启用状态的管理员
        if not is_active and target.role == ROLE_ADMIN:
            await self._ensure_not_last_admin(target.id, "停用")

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

    async def _ensure_not_last_admin(self, target_id: int, action: str) -> None:
        """确保该操作不会让平台失去最后一个启用的管理员。"""
        admins = await self.repo.count_admins()
        target = await self.repo.get_user(target_id)
        target_is_active_admin = (
            target is not None and target.role == ROLE_ADMIN and target.is_active
        )
        if target_is_active_admin and admins <= 1:
            raise UserException(
                code=BusinessCode.FORBIDDEN,
                msg=f"不能{action}最后一个启用状态的管理员，否则将无人可管理后台",
            )

    # ==================== 会话洞察 ====================
    async def conversation_stats(self) -> dict[str, Any]:
        return await self.repo.conversation_stats()

    async def list_conversations(
        self, *, page: int, page_size: int, keyword: str | None = None, user_id: int | None = None
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(page_size, config.ADMIN_PAGE_SIZE_MAX))
        items, total = await self.repo.list_conversations(
            page=page, page_size=page_size, keyword=keyword, user_id=user_id
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
                    "created_at": r.created_at,
                }
                for r in rows
            ],
        }
