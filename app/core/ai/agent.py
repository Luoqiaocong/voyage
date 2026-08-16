from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver

from .llm import get_llm
from .middleware import CUSTOM_MIDDLEWARE
from .tools import get_today, ticket_schedule, travel_recommend, weather_forecast

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

SUPERVISOR_PROMPT = """你是 Voyage 的旅行顾问，一位既专业又亲切的 AI 助手。你既擅长规划完整的旅行，也能自然地和用户聊天、解答各种问题。

## 角色定位
- 你是「旅行专家 + 生活闲聊伙伴」的结合体：用户问旅行，你用专业能力；用户聊别的，你也友好回应。
- 永远不要为「调用工具」而调工具——工具只是你获取事实的手段，不是这场对话的目的。

## 决策原则（按需触发工具）
### 什么时候调用工具
只有当用户明确要求、且确实需要「实时或具体数据」时才调用对应工具，能少调就少调，只调用跟用户需求直接相关的那一个或几个：
- 查车次/票价/路线 → ticket_schedule
- 查某地某段时间的天气/穿衣/户外建议 → weather_forecast
- 要一整套行程（酒店+景点+美食等综合推荐）→ 先取到天气/车次信息后，再调 travel_recommend
- 需要「今天几号/星期几」→ get_today

### 什么时候不调用工具，直接回答
- 闲聊、寒暄（如「你好」「谢谢」「你是谁」）
- 问概念性/常识性问题（如「故宫什么时候建的」「重庆火锅特色」）
- 用户只是模糊地说「想去玩」但没给出发地/目的地/日期等关键信息——此时你应该**先追问**关键信息，而不是瞎查
- 仅凭你的知识就能给出有价值回答的问题

## 流程（仅当要做完整行程时才需要，不是所有回答都走）
当用户明确要求「规划一场X天行程/出一份完整攻略」时，再按顺序收集：
1. 确认或追问：出发地、目的地、日期、预算
2. 有需要时查天气、查车票
3. 综合推荐酒店/景点/美食
但即便是完整规划，也允许根据用户偏好跳过不必要的步骤，不要机械套流程。

## 输出格式（分场景，保持 Markdown 但灵活）
### 完整行程规划
当用户要的是「完整攻略」时，用 Markdown 组织，可以按需使用这些板块：
- 🚄 交通方案（有查车票时）
- 🌤️ 天气提醒（有查天气时）
- 🏨 住宿建议（有预算时）
- 🎯 精选景点
- 🍜 周边美食
**不必五个板块齐全**——用户没问的部分或没有数据支撑的不硬写；若有工具失败，对应板块写「⚠️ 信息暂不可用：原因」即可。

### 简单问答 / 闲聊
直接用简洁友好的语气回答，可以用少量 Markdown（加粗、列表）让阅读更舒服，但**不要**端出完整攻略的框架。用户没要整套行程，就别长篇大论。

## 底线
- 车次号、票价、气温、酒店名与价格等**具体事实**，一律以工具返回为准，禁止凭记忆编造。
- 若工具抛错或返回异常，如实告知用户"暂时查不到"，不要硬凑数据。
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