"""Redis 通用便捷操作（供业务层使用）。"""
from __future__ import annotations

from .client import redis_client


async def verify_code(stored_key: str, value: str) -> bool:
    """取回存储值并与目标值比对；一致时删除（一次性消费）。

    Returns:
        bool: 比对一致并已消费返回 True，否则返回 False
    """
    client = redis_client.get_client()
    stored_value = await client.get(stored_key)
    if stored_value is None or stored_value != value:
        return False
    await client.delete(stored_key)
    return True


async def get_value(stored_key: str) -> str | None:
    """读取存储值；键不存在返回 None。"""
    client = redis_client.get_client()
    return await client.get(stored_key)


async def incr_counter(key: str, window_seconds: int) -> int:
    """原子计数 +1 并返回当前值；首次计数时设置过期时间（限流窗口）。

    固定窗口限流的核心原语：
    - INCR 由 Redis 单线程保证原子性，并发下计数不丢；
    - EXPIRE 带 NX 只在键不存在时设置过期，避免后续请求不断续期；
    - 过期即窗口自动复位，无需后台清理任务。

    Args:
        key: 计数键，如 "rate:send_code:email:xxx@xx.com"
        window_seconds: 窗口时长（秒），过期后计数归零
    """
    client = redis_client.get_client()
    
    async with client.pipeline() as pipe:
        pipe.incr(key) # incr 计数+1
        pipe.expire(key, window_seconds, nx=True)  # nx 只在键不存在时设置过期，避免后续请求不断续期
        result = await pipe.execute()
        return int(result[0])


async def reset_counter(key: str) -> None:
    """清零计数（如登录成功后清空失败计数）。"""
    client = redis_client.get_client()
    await client.delete(key)