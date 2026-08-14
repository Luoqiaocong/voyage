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
    _instance: CompiledStateGraph | None = None
    _checkpointer: BaseCheckpointSaver | None = None

    @classmethod
    def initialize(cls, checkpointer: BaseCheckpointSaver) -> None:
        if cls._instance is not None:
            return

        cls._checkpointer = checkpointer
        cls._instance = create_agent(
            model=get_llm(),
            tools=[],
            checkpointer=checkpointer,
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