"""给动态加载的 MCP 工具套上缓存与埋点。

为什么需要这个模块：
    tools/cached_tools.py 里的三个工具是**手写包装**的——函数签名明确，
    可以逐个 @tool 重写。但 travel 子 Agent 的工具来自
    get_namespace_tools("travel")，是运行时动态拿到的，事先不知道有哪些，
    没法手写。于是需要一层通用包装。

不加会怎样（实测）：
    travel 子 Agent 内部要做多次网页搜索与抓取，冷启动一次
    travel_recommend 耗时约 120 秒。而这些搜索结果在几十分钟内是稳定的，
    同一目的地被反复询问时每次都重跑整套网络请求，纯属浪费。

设计取舍：
    - 只包装异步可调用对象，同步的跳过（本项目与 MCP 交互都是异步）
    - 参数按 schema 重建，保证工具对模型暴露的接口完全不变
    - 单个工具包装失败只跳过该工具并记日志，不影响其余工具可用
"""
from __future__ import annotations

import inspect
from typing import Any

from langchain_core.tools import StructuredTool

from app.core.ai.cache import cached_tool_call
from app.shared.utils import log


def _wrap_one(t) -> Any:
    """包装单个工具；无法包装时原样返回。"""
    name = getattr(t, "name", None)
    schema = getattr(t, "args_schema", None)
    fn = getattr(t, "coroutine", None) or getattr(t, "func", None)

    # 缓存需要按参数构造键，故必须有 schema；同步工具不走这条路
    if not name or schema is None or fn is None or not inspect.iscoroutinefunction(fn):
        return t

    async def _call(**kwargs: Any) -> str:
        # 透传全部参数给原工具，只在其外层做缓存与埋点
        text, _hit = await cached_tool_call(
            name, kwargs, lambda: fn(**kwargs)
        )
        return text

    _call.__name__ = f"{name}_cached"

    try:
        return StructuredTool.from_function(
            coroutine=_call,
            name=name,
            description=getattr(t, "description", "") or "",
            args_schema=schema,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(f"[toolcache] 包装 {name} 失败，将不带缓存使用: {exc}")
        return t


def with_cache(tools: list[Any]) -> list[Any]:
    """给一批工具套上缓存与埋点，返回新列表。"""
    wrapped = []
    n_cached = 0
    for t in tools:
        w = _wrap_one(t)
        if w is not t:
            n_cached += 1
        wrapped.append(w)
    log.info(f"[toolcache] travel 命名空间工具 {len(tools)} 个，其中 {n_cached} 个已接入缓存")
    return wrapped
