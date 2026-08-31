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