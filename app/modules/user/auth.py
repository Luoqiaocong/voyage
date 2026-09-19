import re

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
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
        except (Argon2Error, InvalidHashError):
            # InvalidHashError 继承自 ValueError 而非 Argon2Error，需同时捕获，
            # 兜底"数据库里存了损坏哈希"之类的情况，统一视为密码错误
            return False


def password_weak_reason(password: str) -> str | None:
    """返回密码不合规的**具体原因**；合规返回 None。

    抽成纯函数的原因：同一条规则要在两处生效——
      · schema 层：请求体校验阶段就拦下，避免无效请求进入业务逻辑
      · service 层（validate_password_strength）：兜住绕过 schema 的调用
        （CLI 脚本、内部调用）
    若两处各写一套，早晚漂移（一边说「至少 8 位」另一边还多要求大小写，
    用户就会遇到「前端校验通过、后端却拒绝」）。
    """
    if len(password) < 8:
        return "密码长度至少 8 位"
    if not re.search(r"[a-z]", password):
        return "密码需要包含小写字母"
    if not re.search(r"[A-Z]", password):
        return "密码需要包含大写字母"
    if not re.search(r"[0-9]", password):
        return "密码需要包含数字"
    return None


def validate_password_strength(password: str) -> None:
    """检查密码强度；不合规抛业务异常，消息即具体原因。"""
    reason = password_weak_reason(password)
    if reason:
        raise UserException(code=BusinessCode.USER_PWD_WEAK, msg=reason)


hashids = Hashids(salt=config.HASH_SALT, min_length=12)


def get_hashed_id(real_id: int) -> str:
    """将真实ID转换为哈希ID"""
    return hashids.encode(real_id)


def get_real_id(hashed_id: str) -> int | None:
    """从哈希ID还原真实ID，失败返回 None"""
    decoded = hashids.decode(hashed_id)
    return decoded[0] if decoded else None
