from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.shared.utils import log

from .date_context import inject_current_date
from .llm import TaskKind, get_task_llm
from .middleware import CUSTOM_MIDDLEWARE
from .tools import (
    ticket_schedule_cached,
    travel_recommend_cached,
    weather_forecast_cached,
)

# supervisor 的工具集：带缓存与埋点的版本（见 tools/__init__.py 说明）。
# 抽成模块级常量，避免 initialize 与 apply_memory 两处各写一遍导致漏改。
#
# 这里**不包含 get_today**：当前日期由 date_context 中间件注入系统提示词。
# 日期是服务端每次调用都确切知道的常量，让模型为此跑一次完整工具链路
# 既不必要，界面上也会多出一条「获取当前日期」，
# 用户看到会疑惑「这也要查」。安全性不变——日期仍由我们提供，
# 而非取自模型的记忆。
AGENT_TOOLS = [
    ticket_schedule_cached,
    weather_forecast_cached,
    travel_recommend_cached,
]

# 中间件清单 = 通用中间件 + 日期注入。
# 日期注入放在最后：它在每轮模型调用前把原始 system message 重新组装
# （原提示词 + 当前日期），若放在其它中间件之前，那些中间件看到的
# system message 就会是带日期的版本，不利于各自独立判断。
AGENT_MIDDLEWARE = [*CUSTOM_MIDDLEWARE, inject_current_date]

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

注意：**当前日期已经直接写在你的系统提示词末尾**，无需（也没有工具可以）查询。
需要把「明天/后天/本周五」换算成具体日期时，直接使用那里的日期即可，
自然地在回答里用具体日期，不要解释你是怎么知道今天日期的。

### 什么时候不调用工具，直接回答
- 闲聊、寒暄（如「你好」「谢谢」「你是谁」）
- 问概念性/常识性问题（如「故宫什么时候建的」「重庆火锅特色」）
- 用户只是模糊地说「想去玩」但没给出发地/目的地/日期等关键信息——此时你应该**先追问**关键信息，而不是瞎查
- 仅凭你的知识就能给出有价值回答的问题

### 先看对话里有没有，再决定要不要查（重要）
**前面几轮的工具调用结果仍保留在上下文中，可以直接引用，不要重复查询。**
每次准备调用工具前，先问自己：这个信息我是不是已经查过了？

反例（都是实际会出错的）：
- 前面已查过「广州南→北京西、10 月 1 日」的车次，用户接着说
  「那就基于这个车票信息帮我安排美食和景点」
  → 应当**直接用已有的车次结果**排行程，不要再调 ticket_schedule。
  用户说的是「基于这个」，重复查等于没听懂。
- 前面已查过成都的天气，用户接着问「那带什么衣服」→ 直接用已有天气回答。
- 用户在一轮里从「查车票」推进到「做完整规划」→ 车票这一环已完成，
  直接进入下一环，不要从头再走一遍流程。

什么时候**才**需要重新查：关键参数变了（换出发地/目的地/日期/人数）、
用户明确要求「重新查一次」、之前那次调用失败需要重试、
或已有结果与本次需求确实无关（例如问的是另一个城市）。

判断依据是**参数是否相同**，不是「这轮提到了什么」。

### 失败时不要用相同参数连续重试
某个工具刚失败过时，用完全相同的参数重试几乎不会得到不同结果。
应当如实告知「暂时查不到 XXX」，并说明可以先用已有信息推进哪些部分。

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
    _memory_context: str = ""

    @classmethod
    def initialize(cls, checkpointer: BaseCheckpointSaver) -> None:
        if cls._instance is not None:
            return

        cls._checkpointer = checkpointer
        cls._instance = create_agent(
            model=get_task_llm(TaskKind.CHAT),
            tools=AGENT_TOOLS,
            checkpointer=checkpointer,
            middleware=AGENT_MIDDLEWARE,
            system_prompt=cls._compose_prompt(),
        )

    @classmethod
    def _compose_prompt(cls) -> str:
        """把长期记忆拼到监督提示词之后。

        为什么用「拼接」而不是让模型调用工具去查记忆：
        旅行场景的记忆量很小（通常 5-15 条），全量注入开销可忽略；
        工具方式需要模型自己想起去查，容易被忽略。代价是条数必须收敛，
        故 MemoryService 侧设了上限并按置信度截断。
        """
        if not cls._memory_context:
            return SUPERVISOR_PROMPT
        return f"{SUPERVISOR_PROMPT}\n\n{cls._memory_context}"

    @classmethod
    def apply_memory(cls, memory_context: str) -> None:
        """按当前用户设置长期记忆上下文；仅在文本真正变化时重建 agent。

        同一用户的连续多轮对话不会重复构建，避免每轮都付出 create_agent 开销。
        """
        new_context = memory_context or ""
        if new_context == cls._memory_context:
            return
        cls._memory_context = new_context
        if cls._checkpointer is not None:
            cls._instance = create_agent(
                model=get_task_llm(TaskKind.CHAT),
                tools=AGENT_TOOLS,
                checkpointer=cls._checkpointer,
                middleware=AGENT_MIDDLEWARE,
                system_prompt=cls._compose_prompt(),
            )
            log.info(f"[memory] agent 已按新记忆重建（长度 {len(new_context)}）")

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
        cls._memory_context = ""