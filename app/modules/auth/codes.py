"""邮箱验证码 / 重置令牌的 Redis 生命周期管理。

集中维护键格式、TTL、签发、校验与一次性消费，
业务层（auth / user service）只调用这里的函数，不直接碰 Redis。
"""
from __future__ import annotations

import hashlib
import secrets
import string

from app.core.business.code import BusinessCode
from app.core.business.exception import AuthException
from app.shared.redis import get_value, redis_client, verify_code
from app.shared.utils import send_verification_code

from .constants import (
    VERIFY_CODE_KEY_PREFIX,
    VERIFY_CODE_LENGTH,
    VERIFY_CODE_TTL_SECONDS,
    VERIFY_TOKEN_PREFIX,
    VERIFY_TOKEN_TTL_SECONDS,
)


def create_reset_token() -> str:
    """生成高强度随机重置令牌（256 位随机，无需加密存储）。"""
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """对重置令牌做 SHA-256 摘要，避免明文令牌落入 Redis。"""
    return hashlib.sha256(token.encode()).hexdigest()


def _code_key(email: str) -> str:
    return f"{VERIFY_CODE_KEY_PREFIX}{email}"


def _token_key(token: str) -> str:
    return f"{VERIFY_TOKEN_PREFIX}{hash_reset_token(token)}"


async def issue_code(email: str) -> None:
    """签发邮箱验证码：生成 → 发信 → 落库（发信失败抛 MAIL_SEND_FAILED）。"""
    code = "".join(secrets.choice(string.digits) for _ in range(VERIFY_CODE_LENGTH))
    has_send = await send_verification_code(email, code)
    if not has_send:
        raise AuthException(code=BusinessCode.MAIL_SEND_FAILED)
    client = redis_client.get_client()
    await client.set(_code_key(email), code, ex=VERIFY_CODE_TTL_SECONDS)


async def consume_code(email: str, code: str) -> bool:
    """比对验证码并一次性消费；比对一致且已消费返回 True。"""
    return await verify_code(_code_key(email), code)


async def issue_reset_token(email: str) -> str:
    """签发一次性重置令牌（SHA-256 落库），返回明文令牌。"""
    token = create_reset_token()
    client = redis_client.get_client()
    await client.set(_token_key(token), email, ex=VERIFY_TOKEN_TTL_SECONDS)
    return token


async def get_reset_token_email(token: str) -> str | None:
    """读取令牌绑定的邮箱（不消费）。"""
    return await get_value(_token_key(token))


async def delete_reset_token(token: str) -> None:
    """消费（删除）重置令牌。"""
    client = redis_client.get_client()
    await client.delete(_token_key(token))