"""AI 业务工具包：supervisor 使用的 @tool 调度函数。"""
from app.core.ai.tools.travel_tools import (
    get_today,
    ticket_schedule,
    travel_recommend,
    weather_forecast,
)

__all__ = [
    "get_today",
    "ticket_schedule",
    "travel_recommend",
    "weather_forecast",
]
