from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business import BusinessCode, UserException
from app.core.business.exception import AuthException
from app.modules.user.auth import get_hashed_id
from app.modules.user.repo import UserRepo
from app.shared.db import get_db

from .tokens import (
    consume_code,
    create_access_token,
    get_refresh_token_user,
    issue_code,
    issue_reset_token,
)


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
    
    async def issue_access_token(self, refresh_token: str):
        user_id = await get_refresh_token_user(refresh_token)
        if user_id is None:
            raise AuthException(code=BusinessCode.TOKEN_INVALID)
        access_token = create_access_token({"sub": get_hashed_id(user_id)})
        return {"access_token": access_token, "token_type": "bearer"}