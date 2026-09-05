from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.business import BusinessCode, UserException
from app.core.business.exception import AuthException
from app.modules.user.auth import get_hashed_id
from app.modules.user.repo import UserRepo
from app.shared.db import get_db
from app.shared.ratelimit import (
    CODE_EMAIL_LIMIT,
    CODE_EMAIL_WINDOW,
    RESET_EMAIL_LIMIT,
    RESET_EMAIL_WINDOW,
    check_rate_limit,
    email_code_key,
    reset_token_email_key,
)

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
        """签发邮箱验证码（邮箱维度限流：1 小时最多 5 次，防邮件轰炸）。"""
        if await check_rate_limit(email_code_key(email), CODE_EMAIL_LIMIT, CODE_EMAIL_WINDOW):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="验证码发送过于频繁，请稍后再试",
                headers={"Retry-After": str(CODE_EMAIL_WINDOW)},
            )
        await issue_code(email)

    async def issue_reset_token(self, email: str, code: str) -> dict:
        """两步重置第一步：校验验证码后签发一次性重置令牌。

        要求邮箱已注册（user_exists=True）。
        """
        # 邮箱维度限流（防枚举与滥用）：先限流再查用户
        if await check_rate_limit(reset_token_email_key(email), RESET_EMAIL_LIMIT, RESET_EMAIL_WINDOW):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="操作过于频繁，请稍后再试",
                headers={"Retry-After": str(RESET_EMAIL_WINDOW)},
            )

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