from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Callable, Coroutine,Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business import BaseBusinessException


class TransactionMixin:
    _business_exception_type: type[BaseBusinessException] = BaseBusinessException
    db: AsyncSession
    
    
    @asynccontextmanager
    async def transaction_scope(self):
        try:
            yield
            await self.db.commit()
        except self._business_exception_type:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise


''' 
套上这个装饰器会给整个函数加上事务控制，不利于一些不操作数据库的service方法，这种情况自己调用transaction_scope就好了
'''
def transactional(
    func: Callable[..., Awaitable[Any]]
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """
    事务装饰器：为异步类方法自动包裹数据库事务。
    
    被装饰的方法会在执行前后自动开启/提交/回滚事务。
    """
    
    @wraps(func)  # 保留原函数的元数据（名称、文档字符串等），便于调试
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        包装函数的实际逻辑。
        """
        # 1. 获取被装饰方法的 self 实例（假设被装饰的是类方法）
        # 例如：如果调用 user_repo.create_user(...)，args[0] 就是 user_repo 实例
        self_instance = args[0]
        
        # 2. 进入事务上下文
        # transaction_scope() 应返回一个异步上下文管理器
        # 进入时：开启数据库事务
        # 正常退出时：自动提交（commit）
        # 异常退出时：自动回滚（rollback）
        async with self_instance.transaction_scope():
            # 3. 在事务内执行原函数
            # 如果这里抛出异常，事务会回滚；如果成功，事务会提交
            return await func(*args, **kwargs)

    return wrapper