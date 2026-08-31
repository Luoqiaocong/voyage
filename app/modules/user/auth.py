import re

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from hashids import Hashids

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


def validate_password_strength(password: str) -> None:
    """检查密码强度：至少8位，包含大小写字母和数字"""
    rules = [
        (len(password) >= 8, "密码长度至少8位"),
        (bool(re.search(r'[a-z]', password)), "密码需要包含小写字母"),
        (bool(re.search(r'[A-Z]', password)), "密码需要包含大写字母"),
        (bool(re.search(r'[0-9]', password)), "密码需要包含数字"),
    ]
    
    for passed, msg in rules:
        if not passed:
            raise UserException(code=BusinessCode.USER_PWD_WEAK, msg=msg)

# def validate_password_strength(password: str) -> None:
#     """检查密码强度：至少8位，包含大小写字母和数字"""
#     conditions = [
#         len(password) >= 8,
#         bool(re.search(r'[a-z]', password)),
#         bool(re.search(r'[A-Z]', password)),
#         bool(re.search(r'[0-9]', password)),
#     ]
    
#     if not all(conditions):
#         raise UserException(code=BusinessCode.USER_PWD_WEAK)

hashids = Hashids(salt=config.HASH_SALT, min_length=12)


def get_hashed_id(real_id: int) -> str:
    """将真实ID转换为哈希ID"""
    return hashids.encode(real_id)


def get_real_id(hashed_id: str) -> int | None:
    """从哈希ID还原真实ID，失败返回 None"""
    decoded = hashids.decode(hashed_id)
    return decoded[0] if decoded else None
