"""AI 业务工具包：supervisor 使用的 @tool 调度函数。

这里导出的是**带缓存版本**（cached_tools 里重新声明的同名工具），
supervisor 组装 agent 时直接取用即可获得缓存与埋点能力。
原始实现保留在 travel_tools 中不作改动，便于单独测试与回退。

注意：原先这里还导出 get_today，现已移除。
当前日期改由 app/core/ai/date_context.py 的中间件直接注入系统提示词——
日期是服务端每次调用都确切知道的常量，让模型为它跑一次完整工具链路
既不必要，界面上也会多出一条「获取当前日期」让用户困惑。
函数本身仍保留在 travel_tools 中（有单测价值，也便于需要时改回工具形式），
但不再作为工具暴露给模型。
"""
from app.core.ai.tools.cached_tools import (
    ticket_schedule_cached,
    travel_recommend_cached,
    weather_forecast_cached,
)

__all__ = [
    "ticket_schedule_cached",
    "travel_recommend_cached",
    "weather_forecast_cached",
]
