from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver

from .llm import get_llm
from .tools import (
    ticket_schedule,
    travel_recommend,
    weather_forecast,
     get_today
)
from .middleware import CUSTOM_MIDDLEWARE
if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

SUPERVISOR_PROMPT = """你是旅游出行总调度（Supervisor）。你只能通过工具获取事实信息，禁止凭记忆编造车次、票价、天气、酒店价格。

## 强制流程（必须按顺序执行，不可跳过）

### Step 1：并行查票 + 查天气（必须都调用）
在同一轮或连续两轮中必须调用：
1. ticket_schedule(origin, destination, date, requirements)
   - origin / destination / date 从用户原话提取；date 用 YYYY-MM-DD
   - requirements 用自然语言写清：时间段、坐席、排序方式等
2. weather_forecast(date_range, destination)
   - date_range 例如 "2026-08-15 到 2026-08-16"

在拿到上述工具结果之前，禁止输出最终路书。

### Step 2：旅游推荐（必须调用）
在拿到 Step 1 的真实工具返回后，调用：
- travel_recommend(destination, weather_summary, ticket_summary, hotel_budget, hotel_dates, extra_requirements)
  - weather_summary / ticket_summary：尽量粘贴工具返回原文（尤其到站时间/车站）
  - hotel_budget / hotel_dates / extra_requirements：从用户需求提取

### Step 3：汇总输出
仅在以上工具都返回后，用 Markdown 输出：
## 🚄 交通方案
## 🌤️ 天气提醒
## 🏨 住宿建议
## 🎯 精选景点
## 🍜 周边美食

若某工具失败或返回错误，对应章节写「⚠️ 信息暂不可用：原因」，其余章节照常写。

## 禁止事项
- 禁止不调用 ticket_schedule / weather_forecast / travel_recommend 就回答车次、天气、酒店
- 禁止编造具体车次号、票价、气温、酒店名与价格
- 禁止在 Step 1 未完成时调用 travel_recommend
"""


class AgentFactory:
    _instance: CompiledStateGraph | None = None
    _checkpointer: BaseCheckpointSaver | None = None

    @classmethod
    def initialize(cls, checkpointer: BaseCheckpointSaver|None=None) -> None:
        if cls._instance is not None:
            return

        cls._checkpointer = checkpointer
        cls._instance = create_agent(
            model=get_llm(),
            tools=[ticket_schedule, weather_forecast, travel_recommend,get_today],
            checkpointer=checkpointer if checkpointer is not None else None,
            middleware=CUSTOM_MIDDLEWARE,
            system_prompt=SUPERVISOR_PROMPT,
        )

    @classmethod
    def get_agent(cls) -> CompiledStateGraph:
        if cls._instance is None:
            raise RuntimeError("Agent 尚未初始化！请检查 FastAPI lifespan。")
        return cls._instance

    @classmethod
    def get_checkpointer(cls) -> BaseCheckpointSaver:
        if cls._checkpointer is None:
            raise RuntimeError("Checkpointer 尚未初始化！请检查 FastAPI lifespan。")
        return cls._checkpointer

    @classmethod
    def reset(cls) -> None:
        
        cls._instance = None
        cls._checkpointer = None