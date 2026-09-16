"""用量落库后台任务：周期性把 Redis 中的 Token 增量合并进 token_usage 表。

生命周期由 FastAPI lifespan 管理：
- start() 创建任务；
- stop() 取消任务并做最后一次落库，避免进程退出时丢掉最后一段增量。
"""
from __future__ import annotations

import asyncio
import contextlib

from app.config import config
from app.shared.usage_store import flush_pending_usage
from app.shared.utils import log


class UsageFlushTask:
    """周期性落库任务，可安全重复启动/停止。"""

    def __init__(self, interval_seconds: int | None = None) -> None:
        self._interval = interval_seconds or config.USAGE_FLUSH_INTERVAL_SECONDS
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                written = await flush_pending_usage()
                if written:
                    log.info(f"[usage] periodic flush wrote {written} rows")
            except asyncio.CancelledError:
                raise
            except Exception:
                # 单次失败不能终止循环，否则统计会永久停摆
                log.exception("[usage] periodic flush failed")

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._loop(), name="usage-flush")
        log.info(f"[usage] flush task started, interval={self._interval}s")

    async def stop(self) -> None:
        """取消任务并做最后一次落库（尽力而为，不向上抛异常）。"""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        try:
            written = await flush_pending_usage()
            log.info(f"[usage] final flush wrote {written} rows")
        except Exception:
            log.exception("[usage] final flush failed")


# 全局单例：由 lifespan 启停
usage_flush_task = UsageFlushTask()
