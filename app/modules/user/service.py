from typing import Annotated

from fastapi import Depends
from pydantic import EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business import BusinessCode, UserException
from app.modules.auth.tokens import (
    consume_code,
    create_access_token,
    delete_reset_token,
    get_refresh_token_user,
    get_reset_token_email,
    issue_refresh_token,
    revoke_refresh_token,
    revoke_refresh_tokens,
)
from app.modules.conversation.service import ConversationService
from app.shared.db import get_db
from app.shared.db.models import User
from app.shared.utils import TransactionMixin

from .auth import (
    PasswordManager,
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


    async def _verify_email_code(self, email: str, code: str, *, user_exists: bool = False) -> None:
        """校验邮箱验证码（一次性消费）。

        Args:
            email: 邮箱地址
            code: 验证码
            user_exists: True 要求用户已存在（重置/登录）；False 要求用户不存在（注册）；
        """
        user = await self.repo.get_user_dynamic(email=email)

        if not user_exists and user:
            raise UserException(code=BusinessCode.USER_EXIST)

        if user_exists and not user:
            raise UserException(code=BusinessCode.USER_NOT_FOUND)

        if not await consume_code(email, code):
            raise UserException(code=BusinessCode.CODE_VERIFY_FAILED)


    async def _verify_email_token(self, token: str) -> str:
        """校验临时令牌，返回其绑定的邮箱（令牌在改密成功时才消费）。"""
        email = await get_reset_token_email(token)
        if not email:
            raise UserException(code=BusinessCode.TOKEN_INVALID)
        return email


    # ============ 业务方法 ============
    async def to_register(
        self,
        email: EmailStr,
        pwd: str,
        username: str,
        code: str,
    ) -> None:
        """用户注册"""
        # 先做本地参数校验（密码强度），再消费验证码，避免无效请求白白烧掉验证码
        validate_password_strength(pwd)

        await self._verify_email_code(email, code)

        # 密码哈希处理
        hashed_pwd = PasswordManager.hash(pwd)

        # 创建用户（事务）；并发注册同一邮箱时数据库唯一约束报错，转成业务码
        try:
            async with self.transaction_scope():
                return await self.repo.create(email, hashed_pwd, username)
        except IntegrityError:
            raise UserException(code=BusinessCode.USER_EXIST) from None

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
        refresh_token = await issue_refresh_token(user.id)

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
            
        await revoke_refresh_tokens(user_id)  # 注销所有 Refresh Token（强制重新登录）

    async def to_reset_pwd(self, pwd: str, token: str) -> None:
        """两步重置密码：校验临时令牌后更新密码（令牌一次性消费）。"""
        # 校验临时 token
        email = await self._verify_email_token(token)
        user = await self._get_user(email=email)

        validate_password_strength(pwd)

        new_pwd_hash = PasswordManager.hash(pwd)

        # 先提交密码更新；事务成功后再消费令牌（避免 DB 失败导致有效令牌被白白烧掉）
        async with self.transaction_scope():
            await self.repo.modify(new_pwd_hash, user)

        await delete_reset_token(token)
        await revoke_refresh_tokens(user.id)  # 注销所有 Refresh Token（强制重新登录）


    async def to_change_profile(
        self,
        user_id: int,
        user_update_data: dict[str, str],
    ) -> User:
        """修改用户资料"""
        user = await self._get_user(user_id=user_id)

        async with self.transaction_scope():
            return await self.repo.update(user, user_update_data)
        
        
    async def to_logout(self, token: str,user_id:int) -> None:
        if await get_refresh_token_user(token) != user_id:
            raise UserException(code=BusinessCode.TOKEN_INVALID)
        await revoke_refresh_token(token)
        
        
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

        await revoke_refresh_tokens(user.id)  # 注销所有 Refresh Token（强制重新登录）