from typing import Any

from fastapi import Depends
from pydantic import EmailStr
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.user.constants import ROLE_USER
from app.shared.db import get_db
from app.shared.db.config import IS_SQLITE
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
    async def create(
        self,
        email: EmailStr,
        pwd: str,
        username: str,
        *,
        role: str = ROLE_USER,
    ) -> User:
        """创建新用户并返回用户对象。

        role 由调用方决定（默认普通用户）：首个注册用户会成为管理员，
        该判断在 service 层完成，repo 只负责写入。
        """
        user = User(email=email, password=pwd, username=username, role=role)
        self.db.add(user)
        await self.db.flush()
        return user

    async def is_empty_locked(self) -> bool:
        """判断用户表是否为空，并**锁定该表直到事务结束**。

        为什么需要锁：首个注册用户会成为管理员，若两个请求并发注册，
        它们可能都读到「表为空」而双双获得管理员权限。
        这里在事务内对 users 表加锁，使并发的第二个请求排队等待，
        待第一个提交后再读——那时表已非空，自然拿不到管理员。

        不同后端的写法不同：
          - PostgreSQL：LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE
            （只与其它写操作互斥，不阻塞普通读取）
          - SQLite：本身按库级写锁串行化，无需额外加锁

        注意：**必须在事务内调用**，否则锁会在语句结束时立即释放，
        起不到任何保护作用。
        """
        if not IS_SQLITE:
            await self.db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))

        total = (await self.db.execute(select(func.count(User.id)))).scalar_one()
        return total == 0

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
        
        
    async def delete(self, user: User) -> None:
        # 显式加载关联会话，确保 db.delete(user) 时 ORM 级联（cascade=delete-orphan）
        # 一定触发，不依赖调用方"先前已查询该用户会话"的隐式副作用
        await user.awaitable_attrs.conversations
        await self.db.delete(user)
        await self.db.flush()
 