import random
import string

from app.core.business.code import BusinessCode
from app.core.business.exception import AuthException
from app.shared.utils import send_verification_code


class AuthService:
    """认证服务（验证码相关）。"""

    async def send_code(self, email: str) -> None:
        code = "".join(random.sample(string.digits, 6))
        has_send = await send_verification_code(email, code)
        if not has_send:
            raise AuthException(code=BusinessCode.MAIL_SEND_FAILED)