"""Token 用量与平台指标的只读聚合查询（管理端看板数据源）。

采集见 app/core/ai/token.py（LLM 回调写 Redis），落库见 app/shared/usage_store.py。

日期口径统一为 config.APP_TIMEZONE，与采集侧的 record_date 保持一致，
否则跨时区部署时趋势图会整体错位一天。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.shared.db.models import Conversation, Itinerary, TokenUsage, User


def local_today() -> str:
    """今日日期（yyyy-MM-dd，按 APP_TIMEZONE）。"""
    return datetime.now(ZoneInfo(config.APP_TIMEZONE)).strftime("%Y-%m-%d")


def local_yesterday() -> str:
    """昨日日期：用于收尾跨日窗口残留在旧键里的增量。"""
    return (
        datetime.now(ZoneInfo(config.APP_TIMEZONE)) - timedelta(days=1)
    ).strftime("%Y-%m-%d")


def _date_range(days: int) -> list[str]:
    """近 N 天的日期列表（升序，含今日）。"""
    today = datetime.now(ZoneInfo(config.APP_TIMEZONE))
    return [
        (today - timedelta(days=days - 1 - offset)).strftime("%Y-%m-%d")
        for offset in range(days)
    ]


async def get_token_summary(session: AsyncSession, day: str | None = None) -> dict[str, Any]:
    """指定日期的 Token 汇总（默认今日）。"""
    target = day or local_today()
    stmt = select(
        func.coalesce(func.sum(TokenUsage.input_tokens), 0),
        func.coalesce(func.sum(TokenUsage.output_tokens), 0),
        func.coalesce(func.sum(TokenUsage.total_tokens), 0),
        func.coalesce(func.sum(TokenUsage.calls), 0),
    ).where(TokenUsage.record_date == target)
    row = (await session.execute(stmt)).one()
    return {
        "date": target,
        "input_tokens": int(row[0]),
        "output_tokens": int(row[1]),
        "total_tokens": int(row[2]),
        "calls": int(row[3]),
    }


async def get_model_breakdown(
    session: AsyncSession, day: str | None = None
) -> list[dict[str, Any]]:
    """按模型分组的用量（指定日期；不传则统计全部历史）。"""
    stmt = select(
        TokenUsage.model,
        func.sum(TokenUsage.input_tokens),
        func.sum(TokenUsage.output_tokens),
        func.sum(TokenUsage.total_tokens),
        func.sum(TokenUsage.calls),
    ).group_by(TokenUsage.model)
    if day:
        stmt = stmt.where(TokenUsage.record_date == day)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "model": r[0],
            "input_tokens": int(r[1] or 0),
            "output_tokens": int(r[2] or 0),
            "total_tokens": int(r[3] or 0),
            "calls": int(r[4] or 0),
        }
        for r in rows
    ]


async def get_token_trend(session: AsyncSession, days: int = 7) -> list[dict[str, Any]]:
    """近 N 天的 Token 与调用次数趋势（按日期升序，缺失日期补 0）。"""
    dates = _date_range(days)
    stmt = (
        select(
            TokenUsage.record_date,
            func.sum(TokenUsage.total_tokens),
            func.sum(TokenUsage.calls),
        )
        .where(TokenUsage.record_date >= dates[0])
        .group_by(TokenUsage.record_date)
    )
    rows = (await session.execute(stmt)).all()
    by_day = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in rows}
    return [
        {
            "date": day,
            "total_tokens": by_day.get(day, (0, 0))[0],
            "calls": by_day.get(day, (0, 0))[1],
        }
        for day in dates
    ]


async def get_user_growth_trend(session: AsyncSession, days: int = 7) -> list[dict[str, Any]]:
    """近 N 天的新增用户趋势（按日期升序，缺失日期补 0）。

    users.created_at 存 UTC，此处按其日期前缀统计，与本地时区可能有跨日偏差；
    对「增长趋势」这类粗粒度展示可接受，精确的今日口径见 get_platform_counters。
    """
    dates = _date_range(days)
    day_expr = func.substr(User.created_at, 1, 10)
    stmt = (
        select(day_expr.label("day"), func.count(User.id))
        .where(day_expr >= dates[0])
        .group_by(day_expr)
    )
    rows = (await session.execute(stmt)).all()
    by_day = {r[0]: int(r[1] or 0) for r in rows}
    return [{"date": day, "new_users": by_day.get(day, 0)} for day in dates]


async def get_platform_counters(session: AsyncSession) -> dict[str, int]:
    """平台基础计数（用户 / 会话 / 行程）与今日新增、今日活跃用户。"""
    total_users = (await session.execute(select(func.count(User.id)))).scalar_one()
    total_conversations = (
        await session.execute(select(func.count(Conversation.id)))
    ).scalar_one()
    total_itineraries = (
        await session.execute(select(func.count(Itinerary.id)))
    ).scalar_one()

    today = local_today()
    new_users_today = (
        await session.execute(
            select(func.count(User.id)).where(func.substr(User.created_at, 1, 10) == today)
        )
    ).scalar_one()

    # 今日活跃用户：当日产生过会话的去重用户数
    active_users_today = (
        await session.execute(
            select(func.count(func.distinct(Conversation.user_id))).where(
                func.substr(Conversation.created_at, 1, 10) == today
            )
        )
    ).scalar_one()

    return {
        "total_users": int(total_users),
        "total_conversations": int(total_conversations),
        "total_itineraries": int(total_itineraries),
        "new_users_today": int(new_users_today),
        "active_users_today": int(active_users_today),
    }


def estimate_cost_usd(
    breakdown: list[dict[str, Any]], pricing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """按模型单价估算费用（美元），单价单位为「每百万 token」。

    未配置单价的模型按 0 计并单独列出——避免看板显示一个"看起来完整"
    但实为漏算的金额。
    """
    table = pricing if pricing is not None else config.MODEL_PRICING
    total = 0.0
    unpriced: list[str] = []
    for item in breakdown:
        price = table.get(item["model"])
        if not price:
            unpriced.append(item["model"])
            continue
        total += item["input_tokens"] / 1_000_000 * float(price.get("input", 0))
        total += item["output_tokens"] / 1_000_000 * float(price.get("output", 0))
    return {
        "estimated_usd": round(total, 6),
        "currency": "USD",
        "unpriced_models": unpriced,
    }
