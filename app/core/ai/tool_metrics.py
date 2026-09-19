"""工具调用统计回调。

## 为什么改用回调，而不是给每个工具加包装

原先只有 `cached_tools._run_cached` 里调了 `record_tool_call`，覆盖的仅是
**supervisor 的 3 个缓存工具**。而真正干活的是两层子 Agent 里的 MCP 工具
（`travel` 8 个 + `ticket` 8 个），它们由 langchain-mcp-adapters 直接装配，
**没有任何包装层** —— 于是管理端「工具调用」恒为 0。

实测确认（2026-09）：`metrics:*` 里只有 chat / extract 字段，`tool.*` 一个都没有。

改为在 langchain 回调里统一埋点：`on_tool_start` / `on_tool_end` /
`on_tool_error` 对**所有**工具生效，包括子 Agent 与 MCP 工具，
不必逐个改造 16 个工具，将来新增工具也自动覆盖。

## 为什么必须只统计「每层的顶层调用」

同一次用户请求会被观察到多层：

    weather_forecast_cached      ← supervisor 调用（第 1 层）
      └─ weather_forecast        ← 第 1 层的子 Agent 调用（第 2 层）
           ├─ weather_query_15d    ← 第 2 层的子 Agent 调 MCP 工具（第 3 层）
           └─ weather_query_by_area

且**层数取决于缓存命中**：命中时只有第 1 层（上层直接返回缓存），
未命中时展开到第 3 层。若把所有事件都计数，同一个逻辑调用会出现
「命中记 1、未命中记 4」，数字完全不可比。

判据（实测得出，非推测）：`parent_run_id` **不在本次工具 run_id 集合内**
即视为该层的顶层调用。据此每层各记 1 次，命中与未命中口径一致。

指标命名：
    tool.<name>.calls          每个工具被调用次数（含 MCP 工具）
    tool.<name>.errors         失败次数
    tool.<name>.cache_hit/miss 仅缓存包装层有（子 Agent 层不写这条）
    tool.total.calls           所有层合计，用于总览
延迟写入 metrics:lat 的 tool.<name> 桶。
"""
from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from app.shared.utils import log

from app.shared.observability import incr, observe_latency


def _tool_name(serialized: dict | None, kwargs: dict) -> str:
    """取工具名。

    serialized['name'] 是常规来源；MCP 工具在部分版本里只出现在 kwargs 中，
    故做两级兜底。取不到时返回 unknown，宁可记不到名字也不要抛异常 ——
    统计失败绝不能影响主流程。
    """
    name = (serialized or {}).get("name")
    if not name:
        name = kwargs.get("name")
    return str(name) if name else "unknown"


class ToolCallCounter(AsyncCallbackHandler):
    """统计所有工具调用（含子 Agent 与 MCP 工具）。"""

    def __init__(self) -> None:
        super().__init__()
        # run_id -> (工具名, 起始时间)；仅记录「本层顶层」的调用
        self._running: dict[UUID, tuple[str, float]] = {}
        # 本次链路上所有工具的 run_id，用于判断某次调用的 parent 是不是工具
        self._tool_runs: set[UUID] = set()

    async def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            name = _tool_name(serialized, kwargs)
            self._tool_runs.add(run_id)

            # 只统计每层的顶层调用（见模块注释）。嵌套调用直接忽略，
            # 否则缓存命中与未命中的计数会差好几倍。
            if parent_run_id is not None and parent_run_id in self._tool_runs:
                return

            self._running[run_id] = (name, time.perf_counter())
        except Exception:
            log.warning("[metrics] on_tool_start 处理失败")

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            entry = self._running.pop(run_id, None)
            if entry is None:
                return
            name, started = entry
            await self._record(name, ok=True, ms=(time.perf_counter() - started) * 1000)
        except Exception:
            log.warning("[metrics] on_tool_end 处理失败")

    async def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        try:
            entry = self._running.pop(run_id, None)
            if entry is None:
                return
            name, started = entry
            await self._record(name, ok=False, ms=(time.perf_counter() - started) * 1000)
        except Exception:
            log.warning("[metrics] on_tool_error 处理失败")

    @staticmethod
    async def _record(name: str, *, ok: bool, ms: float) -> None:
        await incr(f"tool.{name}.calls")
        if not ok:
            await incr(f"tool.{name}.errors")
        await incr("tool.total.calls")
        await observe_latency(f"tool.{name}", ms)


#: 全局单例。放在 agent 的 config 里，随每次请求传入。
tool_call_counter = ToolCallCounter()
