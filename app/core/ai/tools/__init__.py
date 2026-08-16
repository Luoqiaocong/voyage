"""AI 业务工具包：supervisor 使用的 @tool 调度函数。"""
from app.core.ai.tools.travel_tools import (
    ticket_schedule,
    travel_recommend,
    weather_forecast,
    get_today,
)

__all__ = [
    "ticket_schedule",
    "travel_recommend",
    "weather_forecast",
    "get_today",
]
