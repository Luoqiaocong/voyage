
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from fastapi import Depends
from pydantic import EmailStr

from app.core.business.code import BusinessCode
from app.core.business.exception import UserException
from app.shared.utils import TransactionMixin
from .util import PasswordManager
from app.shared.db.models import User
from app.shared.db import get_db

from .repo import UserRepo


class UserService(TransactionMixin):
    def __init__(
        self,repo: Annotated[UserRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)]  # 掌握事务主动权
    ):
       self.repo = repo
       self.db = db
       
    async def _get_user(self, *, email: str | None = None, user_id: int | None = None) -> User:
        user = await self.repo.get_user_dynamic(user_id=user_id, email=email) # 先查数据库，确保邮箱唯一   
        if not user:    
            raise UserException(code=BusinessCode.USER_NOT_FOUND)
        return user
    
    async def to_register(self, email:EmailStr, pwd:str,username:str):
        existing_user = await self.repo.get_user_dynamic(email=email)  # 先查数据库，确保邮箱唯一
        if existing_user:
            raise UserException(code=BusinessCode.USER_EXIST)
        pwd = PasswordManager.hash(pwd)  # 密码哈希处理
        async with self.transaction_scope():
            return await self.repo.create(email,pwd,username)
    
    async def to_login(self, email:EmailStr, pwd:str):
        
        return self.repo.login(email)