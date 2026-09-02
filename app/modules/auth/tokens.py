"""令牌生命周期管理（auth 模块）。

集中维护验证码 / 重置令牌 / 访问令牌 / 刷新令牌的签发与 Redis 生命周期，
业务层（auth / user service）只调用这里的函数，不直接碰 Redis。
"""
from __future__ import annotations

import hashlib
import secrets
import string
from datetime import UTC, datetime, timedelta

from jose import ExpiredSignatureError, JWTError, jwt

from app.config import config
from app.core.business.code import BusinessCode
from app.core.business.exception import AuthException, UserException
from app.shared.redis import get_value, redis_client, verify_code
from app.shared.utils import send_verification_code

from .constants import (
    REFRESH_KEY_PREFIX,
    REFRESH_USER_KEY_PREFIX,
    VERIFY_CODE_KEY_PREFIX,
    VERIFY_CODE_LENGTH,
    VERIFY_CODE_TTL_SECONDS,
    VERIFY_TOKEN_PREFIX,
    VERIFY_TOKEN_TTL_SECONDS,
)


def create_access_token(data: dict, expire_minutes: int | None = None) -> str:
    """生成 JWT 访问令牌。

    Args:
        data: 要编码的数据（如 {"sub": user_id}）
        expire_minutes: 可选的自定义过期时间（单位：分钟）

    Returns:
        编码后的 JWT 字符串
    """
    to_encode = data.copy()

    # 确定过期时间（分钟数）
    expire_minutes = expire_minutes or config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES

    # 计算过期时间点
    expire = datetime.now(UTC) + timedelta(minutes=expire_minutes)

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        config.JWT_SECRET_KEY,
        algorithm=config.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """解码并校验 JWT 访问令牌，失败抛业务异常，成功返回载荷。"""
    try:
        return jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise UserException(code=BusinessCode.TOKEN_EXPIRED)
    except JWTError:
        raise UserException(code=BusinessCode.TOKEN_INVALID)


def create_refresh_token() -> str:
    """生成长寿命、高强度的全球唯一随机字符串作为 RefreshToken"""
    # 生成 32 字节的十六进制安全随机数（比普通的 UUID 更加防猜测、防碰撞）
    return secrets.token_hex(32)


def create_reset_token() -> str:
    """生成高强度随机重置令牌（256 位随机，无需加密存储）。"""
    return secrets.token_urlsafe(32)


def _token_hash(token: str) -> str:
    """对任意令牌做 SHA-256 摘要，避免明文令牌落入 Redis。"""
    return hashlib.sha256(token.encode()).hexdigest()


def hash_reset_token(token: str) -> str:
    """对重置令牌做 SHA-256 摘要（对外兼容入口）。"""
    return _token_hash(token)


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


# ======================= Refresh Token =======================

def refresh_token_ttl_seconds() -> int:
    """Refresh Token 有效期（秒），与 config.JWT_REFRESH_TOKEN_EXPIRE_DAYS 对齐。"""
    return config.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400


async def issue_refresh_token(user_id: int) -> str:
    """登录时签发 Refresh Token：主键落库（哈希）+ 登记进用户集合（多设备并存）。"""
    token = create_refresh_token()
    token_hash = _token_hash(token)
    client = redis_client.get_client()
    ttl = refresh_token_ttl_seconds()
    async with client.pipeline() as pipe:
        pipe.set(f"{REFRESH_KEY_PREFIX}{token_hash}", user_id, ex=ttl)
        pipe.sadd(f"{REFRESH_USER_KEY_PREFIX}{user_id}", token_hash)
        await pipe.execute()
    return token


async def get_refresh_token_user(token: str) -> int | None:
    """读取 Refresh Token 绑定的用户 id（不消费，供刷新接口重复使用）。

    Redis 中数据异常（非数字）时按无效令牌处理，避免脏数据抛成 500。
    """
    value = await get_value(f"{REFRESH_KEY_PREFIX}{_token_hash(token)}")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def revoke_refresh_token(token: str) -> None:
    """撤销单个 Refresh Token（登出单设备）。"""
    client = redis_client.get_client()
    token_hash = _token_hash(token)
    key = f"{REFRESH_KEY_PREFIX}{token_hash}"
    user_id = await get_value(key)
    await client.delete(key)
    if user_id is not None:
        await client.srem(f"{REFRESH_USER_KEY_PREFIX}{user_id}", token_hash) # type: ignore


async def revoke_refresh_tokens(user_id: int) -> None:
    """撤销某用户的全部 Refresh Token（改密 / 注销 / 强制下线）。"""
    client = redis_client.get_client()
    member_key = f"{REFRESH_USER_KEY_PREFIX}{user_id}"
    token_hashes = await client.smembers(member_key) # type: ignore
    if token_hashes:
        await client.delete(*[f"{REFRESH_KEY_PREFIX}{h}" for h in token_hashes])
    await client.delete(member_key)