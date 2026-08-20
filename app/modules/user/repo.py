from typing import Any

from fastapi import Depends
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db import get_db
from app.shared.db.models import User


class UserRepo:
    def __init__(self, db: AsyncSession = Depends(get_db)):
        self.db = db

    # ============ 基础查询方法 ============
    async def _get_user_base(self, statement) -> User | None:
        """执行查询语句并返回单个用户或 None"""
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    # ============ 查询方法 ============
    async def get_user_dynamic(
        self,
        user_id: int | None = None,
        email: str | None = None,
    ) -> User | None:
        """
        动态查询用户，支持通过 user_id 或 email 查询。
        注：user_id 和 email 不能同时传入。
        """
        # 参数校验（可选）
        if user_id and email:
            raise ValueError("不能同时传入 user_id 和 email")

        # 通过 user_id 查询
        if user_id:
            stmt = select(User).where(User.id == user_id)
            return await self._get_user_base(stmt)

        # 通过 email 查询
        if email:
            stmt = select(User).where(User.email == email)
            return await self._get_user_base(stmt)

        return None

    # ============ 创建方法 ============
    async def create(self, email: EmailStr, pwd: str, username: str):
        """创建新用户并返回用户对象"""
        user = User(email=email, password=pwd, username=username)
        self.db.add(user)
        await self.db.flush()

    # ============ 更新方法 ============
    async def update(
        self,
        user: User,
        user_update_data: dict[str, Any],
    ) -> User:
        """
        更新用户信息并返回更新后的用户对象。
        使用 ORM 方式更新字段，避免使用 Update 语句。
        """
        # 更新字段
        for key, value in user_update_data.items():
            if hasattr(user, key):
                setattr(user, key, value)

        # 刷新到数据库（不提交，由 Service 层控制事务）
        await self.db.flush()

        # 返回更新后的用户对象
        return user

    # ============ 修改密码 ============
    async def modify(self, new_pwd_hash: str, user: User) -> None:
        """修改用户密码"""
        user.password = new_pwd_hash
        await self.db.flush()