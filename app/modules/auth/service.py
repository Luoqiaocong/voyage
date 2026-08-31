from .tokens import issue_code


class AuthService:
    """认证服务（验证码相关）。"""

    async def send_code(self, email: str) -> None:
        await issue_code(email)