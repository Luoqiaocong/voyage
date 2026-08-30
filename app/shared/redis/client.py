"""Redis 异步客户端管理（基础设施层）。

生命周期由 FastAPI 的 lifespan 统一管理：启动时 init_redis()，关闭时 close()。

使用方式：
    from app.shared.redis import redis_client

    redis = redis_client.get_client()
    await redis.set("key", "value", ex=60)
"""
from __future__ import annotations

from redis import asyncio as aioredis

from app.config import config


class RedisManager:
    """Redis 异步管理器：持有全局连接，直接暴露原生 Redis 客户端。"""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def init_redis(self) -> None:
        """初始化 Redis 连接（FastAPI 启动钩子中调用）。

        注意：aioredis 是懒连接，这里只创建客户端，
        首次执行命令时才真正建立连接，因此 Redis 未启动也不会阻塞启动。
        """
        self._redis = aioredis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            decode_responses=True,
        )

    def get_client(self) -> aioredis.Redis:
        """获取原生 Redis 客户端；未初始化时抛错提示。"""
        if self._redis is None:
            raise RuntimeError("Redis 尚未初始化，请在应用启动时调用 init_redis()")
        return self._redis

    async def close(self) -> None:
        """关闭连接（FastAPI 关闭钩子中调用）。"""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


# 全局单例
redis_client = RedisManager()