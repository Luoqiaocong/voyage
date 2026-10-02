import re

import anyio
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from hashids import Hashids

from app.config import config
from app.core.business import BusinessCode, UserException


class PasswordManager:
    """密码管理器"""
    _ph = PasswordHasher()
    # 「用户不存在」时用于抹平时间差的占位哈希；首次使用时惰性生成。
    _dummy_hash: str | None = None

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

    @classmethod
    def _dummy(cls) -> str:
        if cls._dummy_hash is None:
            cls._dummy_hash = cls._ph.hash("__voyage_timing_dummy__")
        return cls._dummy_hash

    @classmethod
    def verify_uniform(cls, plain_password: str, hashed_password: str | None) -> bool:
        """校验密码；hashed 为 None（用户不存在）时做一次等价校验再返回 False。

        若在「用户不存在」分支直接跳过校验，该分支会明显更快，
        攻击者可用响应时间差枚举哪些邮箱已注册。这里保证两条路径
        都执行一次 Argon2 校验，耗时基本相同。
        """
        if not hashed_password:
            cls.verify(plain_password, cls._dummy())
            return False
        return cls.verify(plain_password, hashed_password)


# ---------- 异步包装：Argon2 是 CPU 密集的同步计算 ----------
# 直接在 async 处理函数里调用会阻塞事件循环（实测单次约 70ms），
# 并发登录/注册时所有请求一起卡住。放到线程池执行，让出事件循环。
# 保留同步方法供 CLI 脚本与单测使用，二者语义一致。


async def hash_password_async(password: str) -> str:
    return await anyio.to_thread.run_sync(PasswordManager.hash, password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    return await anyio.to_thread.run_sync(
        PasswordManager.verify, plain_password, hashed_password
    )


async def verify_password_uniform_async(
    plain_password: str, hashed_password: str | None
) -> bool:
    return await anyio.to_thread.run_sync(
        PasswordManager.verify_uniform, plain_password, hashed_password
    )


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
