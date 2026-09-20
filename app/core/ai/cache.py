"""工具结果缓存（Redis）。

为什么值得缓存
--------------
weather_forecast / ticket_schedule / travel_recommend 内部都会再起一个子 agent
去请求外部 MCP 服务，一轮对话里同一个目的地经常被查两次（用户追问、或
模型先查天气再查车次时重复组织上下文）。缓存能显著减少外部依赖调用与等待。

缓存键的两个要点
----------------
1. **参数归一化后参与哈希**：同一组参数的顺序/空白差异不应产生不同缓存项。
2. **含日期维度**（cache_date）：天气、车次这类结果与「哪一天查的」强相关。
   若不带日期，第二天会命中昨天的缓存并返回过期天气——这是最危险的一类 bug。
   故键里显式带上本地日期，跨日自动失效；同时 TTL 也限制在数分钟内，
   避免当天内数据过旧。

降级策略：Redis 不可用时视为「未命中」，直接执行原工具，绝不因缓存故障阻断对话。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.config import config
from app.shared.redis import redis_client
from app.shared.utils import log

CACHE_KEY_PREFIX = "toolcache:"

# 各工具缓存 TTL（秒）。按数据变化速度分级：
# - 天气：一天内可能更新，取 15 分钟
# - 车次/余票：变化较快，取 5 分钟
# - 综合推荐：由前两者派生，取 30 分钟（它本身不依赖实时性强的数据）
# - get_today：纯本地时间，无需缓存（调用开销可忽略）
#
# 以下几项属于 travel 子 Agent 的内部工具（见 tools/wrap_cache.py）。
# 它们做的是网页搜索与抓取，冷启动一轮要一两分钟，而结果在几十分钟内
# 基本不变（酒店名录、景点介绍、地图 POI 都属于慢变数据），
# 故给较长 TTL —— 重复询问同一目的地时能直接省掉整套网络请求。
TOOL_CACHE_TTL: dict[str, int] = {
    "weather_forecast": 15 * 60,
    "ticket_schedule": 5 * 60,
    "travel_recommend": 30 * 60,
    # travel 子 Agent 的内部工具
    "search": 30 * 60,
    "fetch_content": 60 * 60,
    "searchHotels": 60 * 60,
    "hotel_search_and_recommend": 60 * 60,
    "search_map_poi": 60 * 60,
    "getHotelDetail": 60 * 60,
    "getHotelSearchTags": 60 * 60,
    "expand_link": 30 * 60,
}


def _local_date() -> str:
    """本地日期（yyyy-MM-dd），用于让缓存跨日自动失效。"""
    return datetime.now(ZoneInfo(config.APP_TIMEZONE)).strftime("%Y-%m-%d")


def build_cache_key(tool_name: str, args: dict[str, Any]) -> str:
    """构造缓存键：工具名 + 参数哈希 + 本地日期。

    参数先排序后序列化，保证字典顺序不同的等价调用命中同一个键。
    """
    normalized = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"{CACHE_KEY_PREFIX}{tool_name}:{_local_date()}:{digest}"


async def get_cached(tool_name: str, args: dict[str, Any]) -> str | None:
    """读缓存；未命中或 Redis 异常时返回 None。"""
    try:
        value = await redis_client.get_client().get(build_cache_key(tool_name, args))
        return value if isinstance(value, str) else None
    except Exception as exc:  # noqa: BLE001
        # 必须带上异常信息，否则缓存静默失效时无从排查
        log.warning(f"[toolcache] 读取失败，按未命中处理 tool={tool_name}: {type(exc).__name__}: {exc}")
        return None


async def set_cached(tool_name: str, args: dict[str, Any], value: str) -> None:
    """写缓存；TTL 未配置的工具不缓存。失败只记日志。"""
    ttl = TOOL_CACHE_TTL.get(tool_name)
    if not ttl:
        return
    # 过长的结果不缓存：占用内存，且往往是个别用户的长文本，命中率低
    if not value or len(value) > 20_000:
        return
    try:
        await redis_client.get_client().set(
            build_cache_key(tool_name, args), value, ex=ttl
        )
    except Exception as exc:  # noqa: BLE001
        # 同上：必须带异常类型与信息，否则「为什么缓存没生效」无从查起
        log.warning(
            f"[toolcache] 写入失败 tool={tool_name} "
            f"len={len(value)}: {type(exc).__name__}: {exc}"
        )


async def _normalize_result(result: Any) -> str:
    """把工具返回值规整成可写入 Redis 的字符串。

    为什么需要：MCP 工具的返回值并不总是字符串——search 工具返回的是
    形如 (content, artifact) 的元组，直接交给 Redis 会因类型不合法而报错，
    而该异常被上层吞掉后只记一句「写入失败」，导致缓存静默失效、无从排查。

    这里是数据进入缓存的唯一闸口，故在这一层统一处理，
    而不是要求每个工具自己保证返回类型。
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result

    # 协程 / 可等待对象：先取出真实值
    if hasattr(result, "__await__"):
        result = await result
        if isinstance(result, str):
            return result

    # MCP 的内容块：常见形态是 [(type, text), ...] 或 [{"text": ...}, ...]
    if isinstance(result, (list, tuple)):
        parts: list[str] = []
        for item in result:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            elif isinstance(item, (list, tuple)):
                parts.append(" ".join(str(x) for x in item))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)

    return str(result)


async def cached_tool_call(
    tool_name: str, args: dict[str, Any], executor: Callable[[], Any]
) -> tuple[str, bool]:
    """带缓存的工具调用。

    Returns:
        (结果文本, 是否命中缓存)

    注意 executor 是「无参可调用」而非协程对象：未命中时才需要真正执行，
    若先构造协程再判断命中，会造成「协程从未被 await」的告警。
    """
    hit = await get_cached(tool_name, args)
    if hit is not None:
        # 指标埋点：命中率是第 4 期评测口径的核心指标之一
        from app.shared.observability import record_cache_hit

        await record_cache_hit(tool_name, hit=True)
        return hit, True

    from app.shared.observability import record_cache_hit

    await record_cache_hit(tool_name, hit=False)
    raw = executor()
    result = await raw if hasattr(raw, "__await__") else raw
    text = await _normalize_result(result)
    await set_cached(tool_name, args, text)
    return text, False
