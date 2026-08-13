# app/memory.py
from __future__ import annotations

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from app.config import config

_checkpointer: AsyncRedisSaver | None = None

async def init_checkpointer() -> AsyncRedisSaver:
    """应用启动时调用一次：创建连接 + asetup。"""
    global _checkpointer
    # from_conn_string 返回的是 async context manager，这里手动 enter
    cm = AsyncRedisSaver.from_conn_string(
        config.REDIS_URL,
        ttl={
            "default_ttl": 120,       # 分钟 ≈ 2h，可按需改
            "refresh_on_read": True,
        },
    )
    _checkpointer = await cm.__aenter__()
    await _checkpointer.asetup()
    # 把 context manager 挂在实例上，方便关闭
    _checkpointer._cm = cm  # type: ignore[attr-defined]
    return _checkpointer

def get_checkpointer() -> AsyncRedisSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer 未初始化，请先在 lifespan 中调用 init_checkpointer()")
    return _checkpointer

async def close_checkpointer() -> None:
    global _checkpointer
    if _checkpointer is None:
        return
    cm = getattr(_checkpointer, "_cm", None)
    if cm is not None:
        await cm.__aexit__(None, None, None)
    _checkpointer = None