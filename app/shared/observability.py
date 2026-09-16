"""可观测性与评测口径。

为什么需要它
------------
大多数项目只有功能、没有度量：改了提示词或缓存后，说不出「到底变好了没有」。
本模块为三条关键链路建立可比的指标，让优化有据可依、也让问题可定位：

- **工具调用**：调用次数、缓存命中率、失败率、延迟分布
- **结构化提取**：工具调用路径 vs 回退路径的占比、校验通过率
- **对话链路**：端到端延迟分布

为什么延迟用「固定桶计数」而不是保存全量样本
--------------------------------------------
保存每次调用的耗时可以做精确分位数，但内存随调用量线性增长，且需要额外清理。
改用预设桶计数：每次调用只对一个桶做 HINCRBY，写入 O(1)、内存恒定，
读出后按累计占比即可给出 P50/P95 的近似值。对「判断优化是否有效」这个目的，
桶粒度完全够用——我们关心的是「P95 从 3s 档掉到 1s 档」，不是 3120ms 与 3180ms 的差别。

计数全部落在 Redis 的日键上（metrics:{yyyy-MM-dd}），跨日自动分区、可保留 N 天。
Redis 故障时全部降级为「不记指标」——观测绝不能拖垮业务。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.config import config
from app.shared.redis import redis_client
from app.shared.utils import log

METRICS_KEY_PREFIX = "metrics:"
LATENCY_KEY_PREFIX = "metrics:lat:"

# 延迟桶上界（毫秒）。最后一个桶表示「超过前一个上界」。
LATENCY_BUCKETS: tuple[int, ...] = (100, 500, 1_000, 3_000, 10_000)

# 指标保留 30 天
_METRICS_TTL = 86400 * 30


def _today() -> str:
    return datetime.now(ZoneInfo(config.APP_TIMEZONE)).strftime("%Y-%m-%d")


def metrics_key(day: str | None = None) -> str:
    return f"{METRICS_KEY_PREFIX}{day or _today()}"


def latency_key(day: str | None = None) -> str:
    return f"{LATENCY_KEY_PREFIX}{day or _today()}"


def bucket_of(milliseconds: float) -> str:
    """把耗时映射到桶标签，如 le_100 / le_500 / gt_10000。"""
    for bound in LATENCY_BUCKETS:
        if milliseconds <= bound:
            return f"le_{bound}"
    return f"gt_{LATENCY_BUCKETS[-1]}"


async def incr(metric: str, amount: int = 1, *, day: str | None = None) -> None:
    """累加一个计数指标（如 tool.weather.calls）。失败只记日志。"""
    try:
        client = redis_client.get_client()
        key = metrics_key(day)
        async with client.pipeline() as pipe:
            pipe.hincrby(key, metric, amount)
            pipe.expire(key, _METRICS_TTL)
            await pipe.execute()
    except Exception:
        log.warning(f"[metrics] 计数失败 metric={metric}")


async def observe_latency(
    metric: str, milliseconds: float, *, day: str | None = None
) -> None:
    """记录一次耗时到对应桶（metric 作为桶哈希内字段前缀）。"""
    try:
        client = redis_client.get_client()
        key = latency_key(day)
        field = f"{metric}:{bucket_of(milliseconds)}"
        async with client.pipeline() as pipe:
            pipe.hincrby(key, field, 1)
            # 同时记录样本数与总耗时，便于算平均值
            pipe.hincrby(key, f"{metric}:count", 1)
            pipe.hincrby(key, f"{metric}:total_ms", int(milliseconds))
            pipe.expire(key, _METRICS_TTL)
            await pipe.execute()
    except Exception:
        log.warning(f"[metrics] 延迟记录失败 metric={metric}")


# ==================== 语义化的埋点入口 ====================
# 统一在此定义，避免各调用点自己拼 metric 名导致口径不一致。


async def record_tool_call(
    tool: str,
    *,
    cache_hit: bool,
    ok: bool,
    ms: float,
    day: str | None = None,
) -> None:
    """记录一次工具调用。

    day 通常留空（写入今日分区）；显式传入可用于补录历史数据或测试隔离。
    """
    await incr(f"tool.{tool}.calls", day=day)
    await incr(f"tool.{tool}.cache_{'hit' if cache_hit else 'miss'}", day=day)
    if not ok:
        await incr(f"tool.{tool}.errors", day=day)
    await incr("tool.total.calls", day=day)
    await observe_latency(f"tool.{tool}", ms, day=day)


async def record_cache_hit(tool: str, *, hit: bool, day: str | None = None) -> None:
    """缓存命中埋点（由 cache.py 调用；与 record_tool_call 的统计口径互补）。"""
    await incr("cache.total", day=day)
    await incr(f"cache.{tool}.{'hit' if hit else 'miss'}", day=day)


async def record_extraction(
    *, via_tool_call: bool, ok: bool, ms: float, day: str | None = None
) -> None:
    """记录一次结构化提取：走了哪条路径、是否通过校验。"""
    path = "tool_call" if via_tool_call else "prompt_fallback"
    await incr("extract.total", day=day)
    await incr(f"extract.path.{path}", day=day)
    await incr(f"extract.{'ok' if ok else 'fail'}", day=day)
    await observe_latency("extract", ms, day=day)


async def record_chat(*, ok: bool, ms: float, day: str | None = None) -> None:
    """记录一次对话链路（端到端）。"""
    await incr("chat.total", day=day)
    if not ok:
        await incr("chat.errors", day=day)
    await observe_latency("chat", ms, day=day)


# ==================== 读取与聚合 ====================
def _percentiles_from_buckets(buckets: dict[str, int], total: int) -> dict[str, Any]:
    """按累计占比从桶计数推算 P50 / P95。

    返回的是「落在哪个桶上界以内」，属于近似值——这正是桶计数的取舍所在。
    """
    if total <= 0:
        return {"p50": None, "p95": None}

    cumulative = 0
    result: dict[str, Any] = {"p50": None, "p95": None}
    ordered = [f"le_{b}" for b in LATENCY_BUCKETS] + [f"gt_{LATENCY_BUCKETS[-1]}"]
    for label in ordered:
        cumulative += buckets.get(label, 0)
        ratio = cumulative / total
        if result["p50"] is None and ratio >= 0.5:
            result["p50"] = label
        if result["p95"] is None and ratio >= 0.95:
            result["p95"] = label
    # 极端情况兜底：样本极少时可能未达成比例
    if result["p50"] is None:
        result["p50"] = ordered[-1]
    if result["p95"] is None:
        result["p95"] = ordered[-1]
    return result


async def get_metrics(day: str | None = None) -> dict[str, Any]:
    """读取某日的原始指标，并算出命中率、通过率与延迟分位。

    返回结构刻意扁平化：管理端可直接展示，无需再做二次计算。
    """
    target = day or _today()
    try:
        client = redis_client.get_client()
        counters = await client.hgetall(metrics_key(target))
        latency_rows = await client.hgetall(latency_key(target))
    except Exception:
        log.warning("[metrics] 读取失败，返回空指标")
        return {"date": target, "available": False, "counters": {}, "latency": {}}

    counters = {k: int(v) for k, v in counters.items()}
    latency_rows = {k: int(v) for k, v in latency_rows.items()}

    # 把扁平的 tool.x.cache_hit 还原成层级结构，便于前端直接渲染
    tools: dict[str, dict[str, Any]] = {}
    for key, value in counters.items():
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "tool":
            tools.setdefault(parts[1], {})[parts[2]] = value

    for name, stat in tools.items():
        calls = stat.get("calls", 0)
        hits = stat.get("cache_hit", 0)
        stat["cache_hit_rate"] = round(hits / calls, 4) if calls else 0.0
        stat["error_rate"] = round(stat.get("errors", 0) / calls, 4) if calls else 0.0
        buckets = {
            k.split(":", 1)[1]: v
            for k, v in latency_rows.items()
            if k.startswith(f"tool.{name}:") and not k.endswith((":count", ":total_ms"))
        }
        stat.update(
            _percentiles_from_buckets(buckets, latency_rows.get(f"tool.{name}:count", 0))
        )
        count = latency_rows.get(f"tool.{name}:count", 0)
        if count:
            stat["avg_ms"] = round(latency_rows.get(f"tool.{name}:total_ms", 0) / count, 1)

    extract_total = counters.get("extract.total", 0)
    extract_ok = counters.get("extract.ok", 0)
    extract_tool_path = counters.get("extract.path.tool_call", 0)
    extraction = {
        "total": extract_total,
        "ok": extract_ok,
        "fail": counters.get("extract.fail", 0),
        "pass_rate": round(extract_ok / extract_total, 4) if extract_total else 0.0,
        "via_tool_call": extract_tool_path,
        "via_fallback": counters.get("extract.path.prompt_fallback", 0),
        "tool_call_ratio": round(extract_tool_path / extract_total, 4) if extract_total else 0.0,
    }
    chat_total = counters.get("chat.total", 0)
    chat = {
        "total": chat_total,
        "errors": counters.get("chat.errors", 0),
        "error_rate": round(counters.get("chat.errors", 0) / chat_total, 4) if chat_total else 0.0,
    }
    chat_buckets = {
        k.split(":", 1)[1]: v
        for k, v in latency_rows.items()
        if k.startswith("chat:") and not k.endswith((":count", ":total_ms"))
    }
    chat.update(_percentiles_from_buckets(chat_buckets, latency_rows.get("chat:count", 0)))
    chat_count = latency_rows.get("chat:count", 0)
    if chat_count:
        chat["avg_ms"] = round(latency_rows.get("chat:total_ms", 0) / chat_count, 1)

    cache_total = counters.get("cache.total", 0)
    cache = {
        "total": cache_total,
        "hit": sum(v for k, v in counters.items()
                   if k.startswith("cache.") and k.endswith(".hit")),
    }
    cache["hit_rate"] = round(cache["hit"] / cache_total, 4) if cache_total else 0.0

    return {
        "date": target,
        "available": True,
        "tools": tools,
        "extraction": extraction,
        "chat": chat,
        "cache": cache,
        "counters": counters,
    }


async def get_metrics_trend(days: int = 7) -> list[dict[str, Any]]:
    """近 N 天的关键指标趋势（供管理端画图）。"""
    today = datetime.now(ZoneInfo(config.APP_TIMEZONE))
    out: list[dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        snapshot = await get_metrics(day)
        out.append({
            "date": day,
            "tool_calls": (snapshot.get("counters") or {}).get("tool.total.calls", 0),
            "cache_hit_rate": (snapshot.get("cache") or {}).get("hit_rate", 0.0),
            "extract_pass_rate": (snapshot.get("extraction") or {}).get("pass_rate", 0.0),
            "chat_total": (snapshot.get("chat") or {}).get("total", 0),
            "chat_error_rate": (snapshot.get("chat") or {}).get("error_rate", 0.0),
        })
    return out
