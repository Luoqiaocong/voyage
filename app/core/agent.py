from __future__ import annotations
from langchain.agents import create_agent
from app.core.llm import get_llm
from typing import Any
from langgraph.checkpoint.base import BaseCheckpointSaver


SUPERVISOR_PROMPT =\
"""
You are a helpful assistant. Please answer the following question as best as you can.
"""

_agent: Any | None = None
def build_agent(checkpointer: BaseCheckpointSaver) -> Any:
    """用 checkpointer 编译全局 Agent（只应调用一次）。"""
    global _agent
    _agent = create_agent(
        model= get_llm(),  # 模型
        tools=[],          #工具列表
        checkpointer=checkpointer,
        system_prompt=SUPERVISOR_PROMPT,
        # middleware=[...],   # 可选：滑窗 trim
    )
    return _agent

def get_agent() -> Any:
    
    if _agent is None:
        raise RuntimeError("Agent 未初始化，请先在 lifespan 中调用 build_agent()")
    return _agent
