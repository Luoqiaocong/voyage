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

# SQLite 回退模式下检查点文件的路径（仅在不配 DATABASE_URL 时使用）。
#
# 路径层数：本文件在 app/shared/db/ 下，回到项目根需要 **4** 层 parent
# （parent×1=app/shared/db, ×2=app/shared, ×3=app, ×4=项目根）。
# 原本是 ×3，会把检查点写到 app/data/exports/ 而不是项目根的 data/exports/
# —— 与 app/shared/db/config.py 里 DB_PATH 的落点不一致（那边用的是 ×4），
# 导致同一个 data 目录下出现两份分离的 SQLite 数据。
SQLITE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data" / "exports" / "checkpoints.sqlite"
)


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
    """打开 checkpointer，交给 FastAPI lifespan 管理生命周期。

    PostgreSQL 分支**必须用连接池**，不能用 from_conn_string。
    原因见下方 _open_pg_checkpointer 的注释。
    """
    pg_url = resolve_checkpoint_url()

    if pg_url:
        async with _open_pg_checkpointer(pg_url) as saver:
            yield saver
        return

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    log.info(f"[checkpoint] 使用 SQLite 作为会话状态后端: {SQLITE_PATH}")
    async with AsyncSqliteSaver.from_conn_string(str(SQLITE_PATH)) as saver:
        yield saver


@asynccontextmanager
async def _open_pg_checkpointer(pg_url: str):
    """用连接池打开 PG checkpointer。

    为什么不能用 AsyncPostgresSaver.from_conn_string：

    它内部是 `AsyncConnection.connect(...)`，**只持有一条长连接**，
    整进程共用一个 connection 对象。这在本地 PostgreSQL 上没问题，
    但在**托管型 serverless PG（Neon / Supabase 等）上必然出事**：
    服务端会在空闲后主动断开连接，那条连接一旦失效就永远不会重建，
    此后所有读会话的操作全部 500，且无法自愈。

    实测表现（Neon 18.6，闲置一段时间后）：
        psycopg.OperationalError: consuming input failed:
                                  SSL connection has been closed unexpectedly
        psycopg.OperationalError: the connection is closed
    而前端只看到 CORS 报错（500 响应不带 CORS 头），完全掩盖了真实原因。

    改用 AsyncConnectionPool 后：
      - check=check_connection  取用前先校验，死连接直接丢弃重建
      - max_idle / max_lifetime 在服务端断开前主动回收
      - 连接数按需增长（min_size=1 不常驻多余空闲连接）
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

    log.info("[checkpoint] 使用 PostgreSQL 作为会话状态后端（连接池）")

    pool = AsyncConnectionPool(
        conninfo=pg_url,
        min_size=1,
        max_size=8,
        open=False,
        # 取用前校验连接可用性 —— 这是应对 serverless PG 空闲断连的关键
        check=AsyncConnectionPool.check_connection,
        # 比服务端更早回收：Neon 空闲约 5 分钟后可能断连
        max_idle=180.0,
        max_lifetime=1800.0,
        timeout=30.0,
        # 与 from_conn_string 内部保持一致，否则 saver 的批量写入会踩到
        # 预处理语句与事务语义的差异
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await pool.open(wait=True, timeout=30.0)
    try:
        saver = AsyncPostgresSaver(conn=pool)
        # 首次运行自动建表（langgraph 自管的 checkpoint 系列表）。
        # 幂等：已存在时是空操作。
        await saver.setup()
        yield saver
    finally:
        await pool.close()
