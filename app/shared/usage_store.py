"""Token 用量落库（Redis 增量 → token_usage 表）。

为什么不在 LLM 回调里直接写库：
    采集写在流式回复的热路径上。直接在回调里落库会把每次 token 统计
    都变成一次数据库往返（SQLite 时代更是与其文件锁竞争，
    有触发 "database is locked" 的实际风险）。
    因此采集只写 Redis（热路径），落库由后台任务按周期批量完成。

幂等性：
    用 Redis Lua 脚本「读取并清零」原子取出增量，取出的数据不会被第二次读到；
    数据库侧按 (model, record_date) 唯一约束累加 UPSERT。
    即使 flush 与新的 LLM 调用并发，也不会重复计数或丢计数。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.config import IS_POSTGRES
from app.shared.db.models import TokenUsage, UserTokenUsage, utc_now
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


async def drain_day_user_usage(day: str) -> dict[int, dict[str, int]]:
    """原子取出并清零指定日期的**按用户**用量增量。

    返回 {user_id: {metric: value}}；无法解析成整数的字段（例如键被
    别的东西写脏）直接跳过，不让它拖垮整批落库。
    """
    script = _get_drain_script()
    flat = await script(keys=[f"usage:user:day:{day}"])
    usage: dict[int, dict[str, int]] = {}
    for index in range(0, len(list(flat or [])) - 1, 2):
        raw_uid, raw_value = flat[index], flat[index + 1]
        uid_str, _, metric = str(raw_uid).rpartition(":")
        if not uid_str or not metric:
            continue
        try:
            uid = int(uid_str)
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        usage.setdefault(uid, {})[metric] = value
    return usage


def _insert_for_dialect():
    """按当前数据库后端返回对应的 insert 构造器。

    upsert 的 INSERT 语句是方言相关的：
      PostgreSQL 用 postgresql.insert（ON CONFLICT ... DO UPDATE）
      SQLite     用 sqlite.insert（同样是 ON CONFLICT，但构造器不同）
    两者生成的 SQL 语义一致，只是入口不同，故需分支。
    """
    if IS_POSTGRES:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        return pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    return sqlite_insert


def _accumulate(stmt, values: dict) -> object:
    """把 INSERT 改写成「冲突时累加」，而非覆盖（模型维度）。"""
    return stmt.on_conflict_do_update(
        index_elements=[TokenUsage.model, TokenUsage.record_date],
        set_={
            "input_tokens": TokenUsage.input_tokens + values["input_tokens"],
            "output_tokens": TokenUsage.output_tokens + values["output_tokens"],
            "total_tokens": TokenUsage.total_tokens + values["total_tokens"],
            "calls": TokenUsage.calls + values["calls"],
        },
    )


async def _flush_user_usage(session: AsyncSession, day: str) -> int:
    """把某日「按用户」的 Redis 增量合并进 user_token_usage 表。

    与模型维度分开落库：两者是不同聚合维度、写在不同表里
    （理由见 UserTokenUsage 的模型注释）。
    """
    usage = await drain_day_user_usage(day)
    if not usage:
        log.debug(f"[usage] no user-dimension increment for {day}")
        return 0

    insert = _insert_for_dialect()
    written = 0
    for uid, metrics in usage.items():
        values = {
            "user_id": uid,
            "record_date": day,
            "input_tokens": metrics.get("input_tokens", 0),
            "output_tokens": metrics.get("output_tokens", 0),
            "total_tokens": metrics.get("total_tokens", 0),
            "calls": metrics.get("calls", 0),
            "created_at": utc_now(),
        }
        stmt = insert(UserTokenUsage).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[UserTokenUsage.user_id, UserTokenUsage.record_date],
            set_={
                "input_tokens": UserTokenUsage.input_tokens + values["input_tokens"],
                "output_tokens": UserTokenUsage.output_tokens + values["output_tokens"],
                "total_tokens": UserTokenUsage.total_tokens + values["total_tokens"],
                "calls": UserTokenUsage.calls + values["calls"],
            },
        )
        await session.execute(stmt)
        written += 1

    # 成功写入时记一条：便于排查「用户维度是否真的落库」——
    # 这条日志在排障时是唯一能区分「没增量」与「写入被吞」的依据
    log.info(f"[usage] user rows written: {written} for {day}")
    return written


async def flush_usage_to_db(session: AsyncSession, day: str | None = None) -> int:
    """把某日 Redis 增量合并进 token_usage 表。

    Returns:
        写入/更新的模型行数（无增量时为 0）
    """
    target_day = day or local_today()
    usage = await drain_day_usage(target_day)
    user_written = await _flush_user_usage(session, target_day)
    if not usage and not user_written:
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
        stmt = _accumulate(_insert_for_dialect()(TokenUsage).values(**values), values)
        await session.execute(stmt)
        rows_written += 1

    await session.commit()
    log.info(
        f"[usage] flushed {rows_written} model rows + "
        f"{user_written} user rows for {target_day}"
    )
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
