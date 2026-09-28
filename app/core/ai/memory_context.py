"""把「当前用户的长期记忆」注入系统提示词。

## 为什么用上下文变量而不是全局单例

原实现把记忆文本存在 AgentFactory 的类级属性 `_memory_context` 里，
每次请求前用 `apply_memory()` 覆盖它。但 AgentFactory 是进程级全局单例：
两个用户并发对话时，B 的记忆会覆盖 A 的，A 的系统提示词里就可能出现
B 的偏好（跨用户隐私泄露）；同时文本在用户之间来回切换，导致 agent
几乎每轮都要重建（原本设计意图是「同用户多轮只建一次」）。

改为随请求传递的上下文变量：每个请求跑在各自的 asyncio 任务里，
contextvars 天然隔离，并发不会串。date_context 已是同样的模式，
两者的区别只是日期来自服务端常量、记忆来自数据库。
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import SystemMessage

#: 当前请求的用户记忆文本；空串表示无记忆。
_MEMORY_CTX: ContextVar[str] = ContextVar("voyage_memory_ctx", default="")


def get_memory_context() -> str:
    return _MEMORY_CTX.get()


@contextmanager
def use_memory_context(text: str) -> Iterator[None]:
    """在本次请求范围内设置用户记忆；退出时还原，避免泄漏到后续任务。"""
    token = _MEMORY_CTX.set(text or "")
    try:
        yield
    finally:
        _MEMORY_CTX.reset(token)


@dynamic_prompt
def inject_memory(request: ModelRequest) -> SystemMessage:
    """把当前请求的记忆段追加到系统提示词末尾。

    追加而非替换：原提示词承载角色定位与工具使用原则，这里只补一段事实。
    无记忆时原样返回，不引入任何额外内容。
    """
    base = request.system_message
    base_text = ""
    if base is not None:
        content = base.content
        base_text = content if isinstance(content, str) else str(content)

    memory = get_memory_context().strip()
    if not memory:
        return SystemMessage(content=base_text)

    # 幂等：若上游已带记忆段（记忆文本自带标题），先移除旧的再追加，
    # 避免同一段被拼两遍（build_memory_context 返回的文本以该标题开头）。
    header = memory.splitlines()[0].strip() if memory.splitlines() else ""
    if header and header in base_text:
        base_text = base_text.split(header, 1)[0].rstrip()

    return SystemMessage(content=f"{base_text}\n\n{memory}")
