"""Redis 通用便捷操作（供业务层使用）。"""
from __future__ import annotations

from redis import asyncio as aioredis

from .client import redis_client

# 原子「计数 +1 并确保过期时间已设置」。
#
# 为什么用 Lua 而不是 EXPIRE ... NX：
#   NX 选项是 Redis 7.0 才引入的，而本机与不少托管实例仍是 5.x/6.x。
#   在旧版本上直接调用会抛
#     ResponseError: wrong number of arguments for 'expire' command
#   导致所有走限流的接口（登录/注册/发码/重置）返回 500。
#   Lua 在服务端原子执行，同时兼容 Redis 5/6/7。
#
# 语义：
#   1) INCR 计数；
#   2) 仅当计数为 1（本窗口首次请求）时设置 TTL，
#      避免后续请求不断续期导致窗口永不复位；
#   3) 返回当前计数。
#
# 顺带修掉一个隐患：原先用 pipeline 分开执行 INCR 与 EXPIRE，
# 两者之间存在非原子窗口——若进程在此期间中断，会留下「有计数、无过期」的键，
# 该限流窗口将永不复位。Lua 原子完成，消除该问题。
_INCR_WITH_TTL = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

# 脚本在客户端侧缓存 SHA，避免每次请求都重新传输脚本体
_incr_script: aioredis.client.Script | None = None


def _get_incr_script() -> aioredis.client.Script:
    """惰性注册 Lua 脚本（依赖已初始化的 Redis 客户端）。"""
    global _incr_script
    if _incr_script is None:
        _incr_script = redis_client.get_client().register_script(_INCR_WITH_TTL)
    return _incr_script


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
    - 计数与设过期在服务端 Lua 中原子完成，并发下不会出现「有计数无过期」；
    - 仅首次计数设置 TTL，过期即窗口自动复位，无需后台清理任务；
    - 不依赖 Redis 7 的 EXPIRE ... NX，兼容 Redis 5/6/7。

    Args:
        key: 计数键，如 "rate:send_code:email:xxx@xx.com"
        window_seconds: 窗口时长（秒），过期后计数归零
    """
    script = _get_incr_script()
    result = await script(keys=[key], args=[window_seconds])
    return int(result)


async def reset_counter(key: str) -> None:
    """清零计数（如登录成功后清空失败计数）。"""
    client = redis_client.get_client()
    await client.delete(key)