"""记忆提炼后台任务。

为什么放到后台执行而非阻塞对话结束：
    提炼要再调一次 LLM（结构化输出），耗时与一次普通调用相当。
    如果同步等待，用户会在回答生成完之后再多等一次模型往返才能收到结束帧。
    记忆是"后台积累"性质的功能，晚几秒生效完全可以接受。

生命周期与用量落库任务一致：由 FastAPI lifespan 启停，退出前等待在途任务结束
（否则进程退出会丢最后一次提炼）。
"""
from __future__ import annotations

import asyncio
import contextlib

from app.shared.db import AsyncSessionLocal
from app.shared.utils import log


class MemoryExtractTask:
    """记忆提炼任务的持有者：跟踪在途任务，支持优雅停止。"""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._stopping = False

    @property
    def pending(self) -> int:
        return len(self._tasks)

    def submit(self, *, user_id: int, text: str, conversation_id: str | None) -> None:
        """提交一次提炼（不等待结果）。"""
        if self._stopping:
            # 停机中不再接受新任务，避免任务被创建后立刻被取消
            return
        task = asyncio.create_task(
            self._run(user_id=user_id, text=text, conversation_id=conversation_id),
            name=f"memory-extract-{conversation_id or 'unknown'}",
        )
        self._tasks.add(task)
        # 用回调移除已完成的引用，避免集合无限增长（长跑进程的内存泄漏）
        task.add_done_callback(self._tasks.discard)

    async def _run(self, *, user_id: int, text: str, conversation_id: str | None) -> None:
        """独立会话执行提炼：不复用请求级 session（请求早已结束）。"""
        from app.modules.memory.repo import MemoryRepo
        from app.modules.memory.service import MemoryService

        try:
            async with AsyncSessionLocal() as session:
                service = MemoryService(repo=MemoryRepo(db=session), db=session)
                stats = await service.extract_from_text(
                    user_id=user_id, text=text, conversation_id=conversation_id
                )
                if any(stats.values()):
                    log.info(
                        f"[memory] 提炼完成 user={user_id} conv={conversation_id} "
                        f"新增={stats['inserted']} 去重={stats['deduped']} "
                        f"覆盖={stats['overwritten']} 丢弃={stats['rejected']}"
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            # 记忆提炼失败绝不能影响对话主流程，只记录
            log.exception(f"[memory] 提炼任务异常 user={user_id}")

    async def stop(self, timeout: float = 20.0) -> None:
        """停止接受新任务，并等待在途任务完成（带超时兜底）。"""
        self._stopping = True
        if not self._tasks:
            return
        log.info(f"[memory] 等待 {len(self._tasks)} 个提炼任务收尾…")
        _, pending = await asyncio.wait(self._tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        for task in pending:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if pending:
            log.warning(f"[memory] {len(pending)} 个提炼任务超时被取消")


# 全局单例：由 lifespan 启停
memory_extract_task = MemoryExtractTask()
