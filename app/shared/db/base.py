"""
数据库基础配置模块。

本文件是【所有 ORM 模型的基类 + 连接配置】所在地，也是 Alembic 读取表结构真相的源头。

理解下面 import 的含义（重点）：
- create_async_engine : 创建【异步引擎】。引擎 = 数据库连接的底层管理器，
                        是真正负责“如何连上数据库”的地方。
- async_sessionmaker  : 创建【会话工厂】。会话(Session) = 一次业务操作的载体
                        （类似“工作单元”），工厂就是“能批量造出会话”的对象。
- AsyncSession        : 指定会话的具体类型为【异步版】。
- AsyncAttrs          : 供 ORM 模型继承，让异步环境下懒加载关联关系
                        （取到 user 后访问 .conversations 不需要手动 await）。
- DeclarativeBase     : 所有模型(表)的基类。后面 class User(Base) 就是继承它。
                        继承它的类会被 SQLAlchemy 自动转成表结构，并注册进 Base.metadata。
- Path                : 标准库路径工具，让你能用 / 安全地拼接文件系统路径。

心智：引擎管“连接”，会话管“一次操作”，工厂管“怎么造会话”。
"""
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# ---- 数据库文件位置 ----
# 和你的 checkpoints.sqlite 放一起，方便管理
DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "exports" / "app.db"
# ── 这句逐层拆解 ────────────────────────────────────────────────
# __file__          : 当前文件(base.py)的路径
# .resolve()        : 转成绝对路径
# .parent           : 上一级目录。base.py 在 app/shared/db/ 下，
#                     连续 4 个 .parent = db→shared→app→项目根(voyage)
#                  → 最终得到项目根目录/data/exports/app.db
# 目的：不管你在哪运行代码，都能稳定定位数据库文件。
# ────────────────────────────────────────────────────────────────
ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
# ── 数据库连接字符串(URL) ────────────────────────────────────────
# sqlite        : 数据库类型
# +aiosqlite    : 用哪个驱动（aiosqlite = 异步 SQLite 驱动）
# ://           : 分隔符
# {DB_PATH}     : 数据库文件路径
# 记忆格式：数据库+驱动:///路径
# ────────────────────────────────────────────────────────────────

# 连接池配置
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,        # 是否打印执行的 SQL（调试时设 True 能看到所有语句）
    future=True,       # 使用 SQLAlchemy 2.0 新风格 API
    pool_size=15,      # 连接池保持 15 个连接复用
    max_overflow=25,   # 池满后最多再临时开 25 个
    pool_timeout=30,   # 拿不到连接时最多等 30 秒
    pool_pre_ping=True,# 取连接前先 ping，防拿到失效连接
    pool_recycle=3600, # 连接存活 1 小时后回收重连，防数据库端超时断开
    pool_use_lifo=True,# 后进先出取连接，减少频繁建连
)
# 说明：SQLite 单文件、并发低，其实不太需要连接池；
#       这些参数主要是为将来切 PostgreSQL 预留的，保留无害。


# ---- Base（所有 ORM 模型的基类）----
class Base(AsyncAttrs, DeclarativeBase):
    """Declarative Base：所有模型继承它。"""
    # Base.metadata 会收集所有继承本类的表定义——
    # 这正是 alembic env.py 里 target_metadata = Base.metadata 要读取的东西。


# ---- 异步引擎 + 会话工厂 ----
AsyncSessionLocal = async_sessionmaker(
    bind=engine,            # 绑到这个引擎（用它建会话）
    class_=AsyncSession,    # 会话类型 = 异步版
    expire_on_commit=False, # commit 后不把对象属性过期（省一次查询）
    autoflush=False,        # 不自动 flush，让你自己能控制提交时机
)


# ---- FastAPI 依赖注入 session ----
async def get_db():
    # 生成器函数：FastAPI 接口里写 db: AsyncSession = Depends(get_db) 时调用
    async with AsyncSessionLocal() as session:
        try:
            yield session   # 把 session 交给接口使用
        finally:
            await session.close()  # 接口用完【一定】关闭，避免连接泄漏
