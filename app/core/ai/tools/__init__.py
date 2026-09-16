"""AI 业务工具包：supervisor 使用的 @tool 调度函数。

这里导出的是**带缓存版本**（cached_tools 里重新声明的同名工具），
supervisor 组装 agent 时直接取用即可获得缓存与埋点能力。
原始实现保留在 travel_tools 中不作改动，便于单独测试与回退。
"""
from app.core.ai.tools.cached_tools import (
    ticket_schedule_cached,
    travel_recommend_cached,
    weather_forecast_cached,
)
from app.core.ai.tools.travel_tools import get_today

__all__ = [
    "get_today",
    "ticket_schedule_cached",
    "travel_recommend_cached",
    "weather_forecast_cached",
]
