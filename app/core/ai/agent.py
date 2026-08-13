from __future__ import annotations
from fastapi import Request
from langchain.agents import create_agent
from app.core.ai.llm import get_llm
from typing import Any
from langgraph.checkpoint.base import BaseCheckpointSaver


SUPERVISOR_PROMPT =\
"""
You are a helpful assistant. Please answer the following question as best as you can.
"""

class AgentFactory:
    _instance: Any | None = None  # 类级别的内部单例

    @classmethod
    def initialize(cls, checkpointer: BaseCheckpointSaver) -> None:
        """在 lifespan 中调用，初始化并编译 Agent (仅一次)"""
        if cls._instance is not None:
            return
            
        cls._instance = create_agent(
            model=get_llm(),
            tools=[],
            checkpointer=checkpointer,
            system_prompt=SUPERVISOR_PROMPT,
        )

    @classmethod
    def get_agent(cls) -> Any:
        """Service 层随时调用，直接获取已编译的 Agent"""
        if cls._instance is None:
            raise RuntimeError("Agent 尚未初始化！请检查 lifespan 配置。")
        return cls._instance