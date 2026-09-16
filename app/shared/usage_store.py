"""Token 用量落库（Redis 增量 → token_usage 表）。

为什么不在 LLM 回调里直接写库：
    langgraph checkpointer 占用同一个 SQLite 文件（data/exports/checkpoints.sqlite），
    流式回复期间在回调中写库会与其抢锁，有触发 "database is locked" 的实际风险。
    因此采集只写 Redis（热路径），落库由后台任务按周期批量完成。

幂等性：
    用 Redis Lua 脚本「读取并清零」原子取出增量，取出的数据不会被第二次读到；
    数据库侧按 (model, record_date) 唯一约束累加 UPSERT。
    即使 flush 与新的 LLM 调用并发，也不会重复计数或丢计数。
"""
from __future__ import annotations

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.models import TokenUsage, utc_now
from app.shared.redis import redis_client
from app.shared.usage_query import local_today, local_yesterday
from app.shared.utils import log

# 「读取当日哈希并删除」：返回 [field, value, ...]，保证取出的增量只被消费一次
_DRAIN_SCRIPT = """
local data = redis.call('HGETALL', KEYS[1])
if #data > 0 then
    redis.call('DEL', KEYS[1])
end
return data
"""

_drain_script = None


def _get_drain_script():
    """惰性注册取数脚本（依赖已初始化的 Redis 客户端）。"""
    global _drain_script
    if _drain_script is None:
        _drain_script = redis_client.get_client().register_script(_DRAIN_SCRIPT)
    return _drain_script


def _parse_day_usage(flat: list[str]) -> dict[str, dict[str, int]]:
    """把 HGETALL 的扁平结果解析成 {model: {metric: value}}。

    字段格式由 token.py 约定："{model}:{input_tokens|output_tokens|total_tokens|calls}"
    """
    usage: dict[str, dict[str, int]] = {}
    for index in range(0, len(flat) - 1, 2):
        field, raw_value = flat[index], flat[index + 1]
        model, _, metric = field.rpartition(":")
        if not model or not metric:
            continue
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        usage.setdefault(model, {})[metric] = value
    return usage


async def drain_day_usage(day: str) -> dict[str, dict[str, int]]:
    """原子取出并清零指定日期的 Redis 用量增量。"""
    script = _get_drain_script()
    flat = await script(keys=[f"usage:day:{day}"])
    return _parse_day_usage(list(flat or []))


def _accumulate(stmt, values: dict) -> object:
    """把 INSERT 改写成「冲突时累加」，而非覆盖。"""
    return stmt.on_conflict_do_update(
        index_elements=[TokenUsage.model, TokenUsage.record_date],
        set_={
            "input_tokens": TokenUsage.input_tokens + values["input_tokens"],
            "output_tokens": TokenUsage.output_tokens + values["output_tokens"],
            "total_tokens": TokenUsage.total_tokens + values["total_tokens"],
            "calls": TokenUsage.calls + values["calls"],
        },
    )


async def flush_usage_to_db(session: AsyncSession, day: str | None = None) -> int:
    """把某日 Redis 增量合并进 token_usage 表。

    Returns:
        写入/更新的模型行数（无增量时为 0）
    """
    target_day = day or local_today()
    usage = await drain_day_usage(target_day)
    if not usage:
        return 0

    rows_written = 0
    for model, metrics in usage.items():
        values = {
            "model": model,
            "record_date": target_day,
            "input_tokens": metrics.get("input_tokens", 0),
            "output_tokens": metrics.get("output_tokens", 0),
            "total_tokens": metrics.get("total_tokens", 0),
            "calls": metrics.get("calls", 0),
            "created_at": utc_now(),
        }
        stmt = _accumulate(sqlite_insert(TokenUsage).values(**values), values)
        await session.execute(stmt)
        rows_written += 1

    await session.commit()
    log.info(f"[usage] flushed {rows_written} model rows for {target_day}")
    return rows_written


async def flush_pending_usage() -> int:
    """独立事务落库（供后台任务与看板查询调用，不依赖请求级 session）。

    同时处理今日与昨日：避免 23:59 产生的增量长期留在昨日键里无人收取。
    """
    from app.shared.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        written = await flush_usage_to_db(session, local_today())
        written += await flush_usage_to_db(session, local_yesterday())
        return written
