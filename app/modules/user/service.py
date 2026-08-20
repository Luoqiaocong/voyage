from typing import Annotated

from fastapi import Depends
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business.code import BusinessCode
from app.core.business.exception import UserException
from app.shared.db import get_db
from app.shared.db.models import User
from app.shared.utils import TransactionMixin

from .auth import (
    PasswordManager,
    create_access_token,
    create_refresh_token,
    get_hashed_id,
)
from .repo import UserRepo


class UserService(TransactionMixin):
    _business_exception_type = UserException  # 注册为用户异常

    def __init__(
        self,
        repo: Annotated[UserRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],  # 掌握事务主动权
    ):
        self.repo = repo
        self.db = db

    # ============ 内部辅助方法 ============
    async def _get_user(
        self,
        *,
        email: str | None = None,
        user_id: int | None = None,
    ) -> User:
        """获取用户，如果不存在则抛出异常"""
        user = await self.repo.get_user_dynamic(user_id=user_id, email=email)
        if not user:
            raise UserException(code=BusinessCode.USER_NOT_FOUND)
        return user

    # ============ 业务方法 ============
    async def to_register(
        self,
        email: EmailStr,
        pwd: str,
        username: str,
    )->None:
        """用户注册"""
        # 检查邮箱是否已存在
        existing_user = await self.repo.get_user_dynamic(email=email)
        if existing_user:
            raise UserException(code=BusinessCode.USER_EXIST)

        # 密码哈希处理
        hashed_pwd = PasswordManager.hash(pwd)

        # 创建用户（事务）
        async with self.transaction_scope():
            return await self.repo.create(email, hashed_pwd, username)

    async def to_login(
        self,
        email: EmailStr,
        pwd: str,
    ) -> dict:
        """用户登录"""
        user = await self.repo.get_user_dynamic(email=email)

        if user is None or not PasswordManager.verify(pwd, user.password):
            raise UserException(code=BusinessCode.USER_LOGIN_FAILED)

        access_token = create_access_token({"sub": get_hashed_id(user.id)})
        refresh_token = create_refresh_token()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def to_change_pwd(
        self,
        user_id: int,
        current_pwd: str,
        new_pwd: str,
    ) -> None:
        """修改用户密码"""
        user = await self._get_user(user_id=user_id)

        # 验证当前密码
        if not PasswordManager.verify(current_pwd, user.password):
            raise UserException(code=BusinessCode.USER_PWD_AUTH_FAILED)

        # 检查新旧密码是否相同
        if current_pwd == new_pwd:
            raise UserException(code=BusinessCode.USER_PWD_SAME)

        # 哈希新密码
        new_pwd_hash = PasswordManager.hash(new_pwd)

        # 更新密码（事务）
        async with self.transaction_scope():
            await self.repo.modify(new_pwd_hash, user)

    async def to_change_profile(
        self,
        user_id: int,
        user_update_data: dict[str, str],
    ) -> User:
        """修改用户资料"""
        user = await self._get_user(user_id=user_id)

        async with self.transaction_scope():
            return await self.repo.update(user, user_update_data)