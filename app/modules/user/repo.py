from datetime import datetime
from typing import Any

from fastapi import Depends
from pydantic import EmailStr
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db import get_db
from app.shared.db.models import User

from .auth import PasswordManager


class UserRepo:

    def __init__(self, db: AsyncSession = Depends(get_db)):
        self.db = db

    # 基础查询逻辑可以复用
    async def _get_user_base(self, statement) -> User | None:
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    # -------------------- 1. 查询用户 --------------------
    async def get_user_dynamic(
        self,
        user_id: int | None = None,
        email: str | None = None,
    ) -> User | None:
        # 【分支 A】：通过 user_id 查询
        if user_id:
            stmt = select(User).where(User.id == user_id)
            return await self._get_user_base(stmt)

        # 【分支 B】：通过 email 查询
        if email:
            stmt = select(User).where(User.email == email)
            return await self._get_user_base(stmt)

        return None

    # -------------------- 2. 创建用户 --------------------
    async def create(self, email: EmailStr, pwd: str, username: str):
        user = User(email=email, password=pwd, username=username)
        self.db.add(user)
        await self.db.flush()

    # -------------------- 3. 登录查询 --------------------
    async def login(self, email: EmailStr) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        return user if user else None

    # -------------------- 4. 设置 Token --------------------
    async def set_token(self, user_id: int, token: str):
        # 无论之前是否有token，都换成新token
        query = update(User).where(User.id == user_id).values(token=token)
        await self.db.execute(query)
        await self.db.flush()

    # -------------------- 5. 更新用户信息 --------------------
    async def update(self, email: str, user_update_data: dict[str, Any]) -> User | None:
        """更新用户信息并返回更新后的用户对象"""
        # 1. 查询用户是否存在
        user = await self.get_user_dynamic(email=email)
        if not user:
            return None

        # 2. 更新字段（ORM 方式，避免使用 Update 语句）
        for key, value in user_update_data.items():
            if hasattr(user, key):
                setattr(user, key, value)

        # 3. flush 让 SQLAlchemy 同步到数据库（但不提交，由 Service 层控制事务）
        await self.db.flush()

        # 4. 返回更新后的用户对象（此时 user 已经是最新状态）
        return user

    # -------------------- 6. 修改密码 --------------------
    async def change_password(self, new_pwd: str, user: User):
        user.password = PasswordManager.hash(new_pwd)
        await self.db.flush()

    # -------------------- 7. 删除用户 --------------------
    async def delete_user(self, user_email: str):
        stmt = delete(User).where(User.email == user_email)
        row = await self.db.execute(stmt)
        await self.db.flush()
        return row.rowcount > 0  # type: ignore
