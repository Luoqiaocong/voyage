"""langgraph checkpointer 的后端选择。

对话消息状态（历史消息的实体）由 langgraph checkpointer 持久化。
本模块按数据库配置自动选择后端：

  PostgreSQL -> AsyncPostgresSaver（与业务库同库，单一存储引擎）
  SQLite     -> AsyncSqliteSaver（本地开发/测试）

为什么 checkpointer 也要跟着迁：会话消息和业务数据（用户、会话、
行程）本就是同一份业务数据。若业务库用 PG、checkpointer 用 SQLite，
同一个后端要维护两种引擎的备份、迁移与连接管理，没有好处。

注意驱动差异：
  业务库走 SQLAlchemy asyncpg（postgresql+asyncpg://）
  checkpointer 走 psycopg（postgresql://）
两者不通用，故需要把 asyncpg 的连接串转换为 psycopg 能识别的形式。
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import config
from app.shared.db.config import ASYNC_DATABASE_URL, IS_POSTGRES
from app.shared.utils import log

SQLITE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "exports" / "checkpoints.sqlite"


def _to_psycopg_url(url: str) -> str:
    """把 SQLAlchemy 风格的 PG URL 转成 psycopg 可直接使用的形式。

    - 去掉 SQLAlchemy 的方言后缀：postgresql+asyncpg:// -> postgresql://
    - 去掉 SQLAlchemy 专有的 ssl 查询参数（psycopg 用 sslmode 表达）
      Neon 等托管 PG 的连接串常带 ?ssl=require，传给 psycopg 会报未知参数。
    """
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres+asyncpg://", "postgresql://")
    # 移除 ssl/ssl_require 参数，统一改用 sslmode=require
    if "ssl=require" in url or "sslmode=" in url:
        url = re.sub(r"[?&]ssl=require", "", url)
        url = re.sub(r"[?&]sslmode=[^&]*", "", url)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def resolve_checkpoint_url() -> str | None:
    """返回 checkpointer 用的连接串；SQLite 模式返回 None。"""
    explicit = getattr(config, "CHECKPOINT_DATABASE_URL", "") or ""
    if explicit:
        return _to_psycopg_url(explicit)
    if IS_POSTGRES:
        return _to_psycopg_url(ASYNC_DATABASE_URL)
    return None


@asynccontextmanager
async def open_checkpointer():
    """打开 checkpointer，交给 FastAPI lifespan 管理生命周期。"""
    pg_url = resolve_checkpoint_url()

    if pg_url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        log.info("[checkpoint] 使用 PostgreSQL 作为会话状态后端")
        async with AsyncPostgresSaver.from_conn_string(pg_url) as saver:
            # 首次运行自动建表（langgraph 自管的 checkpoints / writes 等表）。
            # 幂等：已存在时是空操作。
            await saver.setup()
            yield saver
        return

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    log.info(f"[checkpoint] 使用 SQLite 作为会话状态后端: {SQLITE_PATH}")
    async with AsyncSqliteSaver.from_conn_string(str(SQLITE_PATH)) as saver:
        yield saver
