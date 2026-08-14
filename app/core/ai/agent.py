from __future__ import annotations

from typing import TYPE_CHECKING
from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver

from .llm import get_llm

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

SUPERVISOR_PROMPT = """
You are a helpful assistant. Please answer the following question as best as you can.
"""


class AgentFactory:
    _instance: CompiledStateGraph | None = None  # 类级别的内部单例对象

    @classmethod
    def initialize(cls, checkpointer: BaseCheckpointSaver) -> None:
        """在 lifespan 中调用，初始化并编译 Agent (仅一次)"""
        if cls._instance is not None:
            return

        # create_agent 内部会编译并返回一个 CompiledStateGraph 实例
        cls._instance = create_agent(
            model=get_llm(),
            tools=[],
            checkpointer=checkpointer,
            system_prompt=SUPERVISOR_PROMPT,
        )

    @classmethod
    def get_agent(cls) -> CompiledStateGraph:
        """Service 层随时调用，直接获取已编译的 Agent"""
        if cls._instance is None:
            raise RuntimeError("Agent 尚未初始化！请检查 FastAPI lifespan 配置。")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """仅供单元测试或热重载时重置单例"""
        cls._instance = None