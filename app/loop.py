"""uvicorn 事件循环工厂（配合 `--loop app.loop:selector_loop_factory` 使用）。

存在的唯一原因：**psycopg 的异步模式不能跑在 ProactorEventLoop 上**，
而 Windows 上 uvicorn 会硬编码返回 ProactorEventLoop：

    def asyncio_loop_factory(use_subprocess=False):
        if sys.platform == "win32" and not use_subprocess:
            return asyncio.ProactorEventLoop
        return asyncio.SelectorEventLoop

注意它连 `--loop asyncio` 都不理会 —— 那个分支不看 loop 参数。
而会话状态由 langgraph 的 psycopg checkpointer 持久化，
所以从 SQLite 切到 PostgreSQL 后，Windows 上必须显式指定本模块。

调用约定（容易写错的一处）：
uvicorn 的 Config.get_loop_factory 会**先调用**本函数并带上
`use_subprocess=` 关键字，把返回值当作 loop 工厂交给 asyncio.Runner。
因此本函数必须**直接返回一个事件循环实例**，而不是返回另一个函数
—— 返回函数会让 Runner 拿到「函数」当循环用，报
`'function' object has no attribute 'create_task'`。

Linux/macOS 默认即 SelectorEventLoop，无需使用本模块。
"""
from __future__ import annotations

import asyncio
import selectors
import sys


def selector_loop_factory(**_kwargs) -> asyncio.AbstractEventLoop:
    """创建一个 SelectorEventLoop 并返回。

    接受并忽略 uvicorn 传入的 use_subprocess 等关键字参数。
    """
    if sys.platform == "win32":
        # Windows 下必须显式给 selector；SelectSelector 是本项目的并发量下
        # 完全够用，且是 psycopg 明确要求的循环类型。
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.SelectorEventLoop()
