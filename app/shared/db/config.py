"""数据库连接配置：URL、连接池参数。

支持两种后端，由环境变量 DATABASE_URL 决定：
  PostgreSQL（主用）  postgresql+asyncpg://user:pwd@host:5432/dbname
  SQLite（兼容/测试） sqlite+aiosqlite:///data/exports/app.db

为什么保留 SQLite：单元测试与随手起一个本地实例时，不该强制先装一套 PG。
但生产/主用环境请配 DATABASE_URL 指向 PostgreSQL。
"""
import os
from pathlib import Path

from app.config import config

# ---- SQLite 回退路径 ----
# 与 checkpoints 放在一起，方便管理；仅在未配置 DATABASE_URL 时使用。
DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "exports" / "app.db"
SQLITE_FALLBACK_URL = f"sqlite+aiosqlite:///{DB_PATH}"


def resolve_database_url() -> str:
    """解析最终使用的数据库 URL。

    优先级：
      1. 环境变量 DATABASE_URL（部署时的标准做法，也便于 Docker 注入）
      2. 配置项 config.DATABASE_URL（.env 里的 DATABASE_URL）
      3. SQLite 回退（本地开发/测试）
    """
    return (
        os.getenv("DATABASE_URL")
        or getattr(config, "DATABASE_URL", None)
        or SQLITE_FALLBACK_URL
    )


ASYNC_DATABASE_URL = resolve_database_url()

# 当前后端类型，供各处按方言分支使用（如 upsert 语句、外键 PRAGMA）
IS_SQLITE = ASYNC_DATABASE_URL.startswith("sqlite")
IS_POSTGRES = ASYNC_DATABASE_URL.startswith("postgresql")

# 连接池配置。
#
# 注意：SQLite 不接受 pool_size / max_overflow 这类参数（它用默认的
# 单连接池实现），传进去会导致连接失败，故只在 PostgreSQL 下启用。
DB_POOL_CONFIG: dict = dict(
    echo=False,          # 是否打印执行的 SQL（调试时设 True）
    future=True,         # SQLAlchemy 2.0 风格 API
    pool_pre_ping=True,  # 取连接前先 ping，防拿到失效连接
)

if IS_POSTGRES:
    DB_POOL_CONFIG.update(
        pool_size=15,          # 池内保持 15 个连接复用
        max_overflow=25,       # 池满后最多再临时开 25 个
        pool_timeout=30,       # 拿不到连接时最多等 30 秒
        pool_recycle=1800,     # 30 分钟回收重连
        # Neon 等 serverless PG 会在空闲后断开连接，且不保证会话粘性，
        # 因此不使用 LIFO（那会让部分连接长期闲置后一起失效）。
        pool_use_lifo=False,
    )
