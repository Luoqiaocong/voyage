import random
import string

from app.core.business.code import BusinessCode
from app.core.business.exception import AuthException
from app.shared.redis import redis_client
from app.shared.utils import send_verification_code

from .constants import VERIFY_CODE_KEY_PREFIX, VERIFY_CODE_TTL_SECONDS,VERIFY_CODE_LENGTH


class AuthService:
    """认证服务（验证码相关）。"""

    async def send_code(self, email: str) -> None:
        code = "".join(random.sample(string.digits, VERIFY_CODE_LENGTH))
        has_send = await send_verification_code(email, code)
        if not has_send:
            raise AuthException(code=BusinessCode.MAIL_SEND_FAILED)
        client = redis_client.get_client()
        await client.set(
            f"{VERIFY_CODE_KEY_PREFIX}{email}",
            code,
            ex=VERIFY_CODE_TTL_SECONDS,
        )