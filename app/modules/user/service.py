from typing import Annotated

from fastapi import Depends
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business import BusinessCode, UserException
from app.modules.conversation.service import ConversationService
from app.shared.db import get_db
from app.shared.db.models import User
from app.shared.utils import TransactionMixin

from .auth import (
    PasswordManager,
    create_access_token,
    create_refresh_token,
    get_hashed_id,
    validate_password_strength,
)
from .repo import UserRepo


class UserService(TransactionMixin):

    def __init__(
        self,
        repo: Annotated[UserRepo, Depends()],
        conv_service: Annotated[ConversationService, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],  # 掌握事务主动权
    ):
        self.repo = repo
        self.conv_service = conv_service
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

        # 密码强校验
        validate_password_strength(pwd)

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

    async def to_change_pwd(self, user_id: int, current_pwd: str, new_pwd: str) -> None:
        """修改用户密码"""
        # 1. 先验证用户身份（旧密码是否正确）
        user = await self._get_user(user_id=user_id)

        if not PasswordManager.verify(current_pwd, user.password):
            raise UserException(code=BusinessCode.USER_PWD_AUTH_FAILED)
        
        # 2. 身份验证通过后，再检查新密码强度
        validate_password_strength(new_pwd)
        
        # 3. 检查新旧密码是否相同
        if current_pwd == new_pwd:
            raise UserException(code=BusinessCode.USER_PWD_SAME)
        
        # 4. 哈希新密码
        new_pwd_hash = PasswordManager.hash(new_pwd)
        
        # 5. 更新密码（事务）
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
        
    async def to_delete_user(self, user_id: int) -> None:
        """用户注销（硬删除）。

        顺序：先清该用户会话的 langgraph checkpoint（外部存储），
        再在同一事务内删除会话行与用户行（显式删除，不依赖 ORM 级联，保证原子）。
        """
        user = await self._get_user(user_id=user_id)

        # 1. 先清 checkpoint（外部存储无法参与事务；失败残留由孤儿清理函数兜底）
        await self.conv_service.delete_checkpoints_for_user(user.id)

        # 2. 会话行 + 用户行同事务删除（同一请求共享同一数据库会话）
        async with self.transaction_scope():
            await self.conv_service.delete_conversation_rows(user.id)
            await self.repo.delete(user)
