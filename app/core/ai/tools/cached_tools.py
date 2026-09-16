"""带缓存的工具定义。

刻意用「显式包装」而不是在两个原工具函数里各插一段缓存逻辑：
- 缓存的边界（哪些工具缓存、哪些不缓存）一眼可见，而不是散落在函数体里；
- 原工具函数保持纯粹（只管业务），便于单独测试与复用；
- get_today 不缓存——它是纯本地时间计算，调用开销可忽略，缓存反而有害
  （会返回过期时间）。

缓存的键包含「今天」的日期，因此跨日自动失效；这也是必须的，
否则第二天会命中昨天的缓存返回过期天气。
"""
import time

from langchain.tools import tool

from app.core.ai.cache import cached_tool_call
from app.core.ai.tools.travel_tools import (
    ticket_schedule as _ticket_schedule,
)
from app.core.ai.tools.travel_tools import (
    travel_recommend as _travel_recommend,
)
from app.core.ai.tools.travel_tools import (
    weather_forecast as _weather_forecast,
)
from app.shared.observability import record_tool_call


async def _run_cached(tool_name: str, args: dict, executor) -> str:
    """统一入口：带缓存执行 + 埋点（调用次数/命中/失败/延迟）。"""
    started = time.perf_counter()
    ok = True
    cache_hit = False
    try:
        text, cache_hit = await cached_tool_call(tool_name, args, executor)
        return text
    except Exception:
        ok = False
        raise
    finally:
        await record_tool_call(
            tool_name,
            cache_hit=cache_hit,
            ok=ok,
            ms=(time.perf_counter() - started) * 1000,
        )


@tool
async def ticket_schedule_cached(
    origin: str,
    destination: str,
    date: str,
    requirements: str,
) -> str:
    """查询火车票/车次：当用户明确要查出发地与目的地之间的车票、票价、车次、时刻、坐席余票时调用。

    仅在用户明确给出（或能自然推断出）出发地、目的地、日期时使用；缺任一关键信息时请先向用户追问，不要乱猜。

    参数:
        origin: 出发地（如 北京西）
        destination: 目的地（如 西安北）
        date: 出发日期，YYYY-MM-DD
        requirements: 额外约束，如时间段、坐席、排序
    """
    origin, destination, date = origin.strip(), destination.strip(), date.strip()
    if not (origin and destination and date):
        return "ERROR: origin/destination/date 均为必填，请重新调用并补全。"

    requirements = (requirements or "").strip()
    # 缓存键必须用**与内层调用完全一致的参数**，否则外层传入的空白/大小写差异
    # 会让同一个逻辑请求产生不同键，缓存命中率随之下降。
    args = {
        "origin": origin,
        "destination": destination,
        "date": date,
        "requirements": requirements,
    }
    return await _run_cached(
        "ticket_schedule",
        args,
        lambda: _ticket_schedule.ainvoke(args),
    )


@tool
async def weather_forecast_cached(
    date_range: str,
    destination: str,
) -> str:
    """查询某地某段时间的天气，并给出穿衣与户外建议：当用户明确要查目的地天气、气温、是否适合出行时调用。

    仅在用户明确给出目的地和日期范围时使用；缺信息时先补问。若用户只是闲聊或问常识性天气知识，直接回答即可，不必调用。

    参数:
        date_range: 如 "2026-08-15 到 2026-08-16"
        destination: 如 "西安"
    """
    destination = destination.strip()
    date_range = date_range.strip()
    if not destination or not date_range:
        return "ERROR: destination 与 date_range 均为必填。"

    args = {"destination": destination, "date_range": date_range}
    return await _run_cached(
        "weather_forecast",
        args,
        lambda: _weather_forecast.ainvoke(args),
    )


@tool
async def travel_recommend_cached(
    destination: str,
    weather_summary: str,
    ticket_summary: str,
    hotel_budget: str,
    hotel_dates: str,
    extra_requirements: str,
    mode: str = "full",
) -> str:
    """综合推荐酒店、景点、美食：当用户要「一整套行程/完整攻略/住在哪吃啥玩啥」时才调用。

    这是在已拿到天气与车次信息之后做的综合推荐。若用户只问单个信息（比如只问景点、只问吃），
    不必硬凑整套，可直接基于已有信息回答。

    参数:
        destination: 目的地
        weather_summary: 天气工具返回摘要（尽量原文）
        ticket_summary: 票务工具返回摘要（含到站时间/车站），没有可填空字符串
        hotel_budget: 如 "500元以内"，没有预算信息传空
        hotel_dates: 如 "2026-08-14 入住 2026-08-16 退房"，没有传空
        extra_requirements: 如 "陕菜、商务型、靠近西安北站"，没有传空
        mode: "full"（完整攻略：酒店+景点+美食）或 "brief"（精简要点，用户只要快速建议时用）
    """
    destination = destination.strip()
    if not destination:
        return "ERROR: destination 必填。"

    args = {
        "destination": destination,
        "weather_summary": weather_summary or "",
        "ticket_summary": ticket_summary or "",
        "hotel_budget": hotel_budget or "",
        "hotel_dates": hotel_dates or "",
        "extra_requirements": extra_requirements or "",
        "mode": mode,
    }
    return await _run_cached(
        "travel_recommend",
        args,
        lambda: _travel_recommend.ainvoke(dict(args)),
    )
