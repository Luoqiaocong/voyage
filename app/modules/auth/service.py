import asyncio
import random
import string

from app.core.business.code import BusinessCode
from app.core.business.exception import AuthException
from app.shared.utils import send_verification_code



class AuthService:

    def __init__(self) -> None:
        pass
    
    async def send_code(self,email: str):
        code = ''.join(random.sample(string.digits, 6))
        has_send = await send_verification_code(email,code,"注册",expire_minutes=3)
        if not has_send:
            raise AuthException(code = BusinessCode.MAIL_SEND_FAILED)