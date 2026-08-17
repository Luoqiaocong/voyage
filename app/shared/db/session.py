"""Session：异步引擎 + 会话工厂 + FastAPI 依赖注入 get_db。"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import ASYNC_DATABASE_URL, DB_POOL_CONFIG

# 异步引擎（连接管理器）
engine = create_async_engine(ASYNC_DATABASE_URL, **DB_POOL_CONFIG)


# 会话工厂：用于批量造出"一次业务操作"的会话
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 后不把对象属性过期（省一次查询）
    autoflush=False,         # 不自动 flush，让你自己能控制提交时机
)


# FastAPI 依赖注入：接口里 db: AsyncSession = Depends(get_db) 时调用
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session   # 把 session 交给接口使用
        finally:
            await session.close()  # 接口用完【一定】关闭，避免连接泄漏
