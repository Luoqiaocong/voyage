from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business import BusinessCode, UserException
from app.modules.user.repo import UserRepo
from app.shared.db import get_db

from .tokens import consume_code, issue_code, issue_reset_token


class AuthService:
    """认证服务（验证码 / 重置令牌签发）。"""

    def __init__(
        self,
        repo: Annotated[UserRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        self.repo = repo
        self.db = db

    async def send_code(self, email: str) -> None:
        """签发邮箱验证码。"""
        await issue_code(email)

    async def issue_reset_token(self, email: str, code: str) -> dict:
        """两步重置第一步：校验验证码后签发一次性重置令牌。

        要求邮箱已注册（user_exists=True）。
        """
        user = await self.repo.get_user_dynamic(email=email)
        if not user:
            raise UserException(code=BusinessCode.USER_NOT_FOUND)

        if not await consume_code(email, code):
            raise UserException(code=BusinessCode.CODE_VERIFY_FAILED)

        token = await issue_reset_token(email)
        return {"token": token}