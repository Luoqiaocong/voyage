import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from hashids import Hashids
from jose import jwt

from app.config import config
from app.core.business import BusinessCode, UserException


class PasswordManager:
    """密码管理器"""
    _ph = PasswordHasher()

    @classmethod
    def hash(cls, password: str) -> str:
        return cls._ph.hash(password)

    @classmethod
    def verify(cls, plain_password: str, hashed_password: str) -> bool:
        try:
            return cls._ph.verify(hashed_password, plain_password)
        except VerifyMismatchError:
            return False


def validate_password_strength(password: str):
    """检查密码强度"""
    if len(password) < 8:
        raise UserException(code=BusinessCode.USER_PWD_WEAK)
    if not re.search(r'[a-z]', password):
        raise UserException(code=BusinessCode.USER_PWD_WEAK)
    if not re.search(r'[A-Z]', password):
        raise UserException(code=BusinessCode.USER_PWD_WEAK)
    if not re.search(r'[0-9]', password):
        raise UserException(code=BusinessCode.USER_PWD_WEAK)


def create_access_token(
    data: dict,
    expires_delta: Optional[int] = None  # 改为 int，单位：分钟
) -> str:
    """
    生成 JWT 访问令牌

    Args:
        data: 要编码的数据（如 {"sub": user_id}）
        expires_delta: 可选的自定义过期时间（单位：分钟）

    Returns:
        编码后的 JWT 字符串
    """
    to_encode = data.copy()

    # 确定过期时间（分钟数）
    expire_minutes = expires_delta or config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES

    # 计算过期时间点
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        config.JWT_SECRET_KEY,
        algorithm=config.JWT_ALGORITHM,
    )


def create_refresh_token() -> str:
    """生成长寿命、高强度的全球唯一随机字符串作为 RefreshToken"""
    # 生成 32 字节的十六进制安全随机数（比普通的 UUID 更加防猜测、防碰撞）
    return secrets.token_hex(32)


hashids = Hashids(salt=config.HASH_SALT, min_length=12)


def get_hashed_id(real_id: int) -> str:
    """将真实ID转换为哈希ID"""
    return hashids.encode(real_id)


def get_real_id(hashed_id: str) -> int | None:
    """从哈希ID还原真实ID，失败返回 None"""
    decoded = hashids.decode(hashed_id)
    return decoded[0] if decoded else None
