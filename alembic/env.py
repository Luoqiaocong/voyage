# ── env.py 是什么？── alembic 的“接线员” ──────────────────────────
# 它不包含任何建表逻辑，只负责告诉 Alembic 两件事：
#   1) 连哪个数据库（sqlalchemy.url，来自 alembic.ini）
#   2) 我的表模型长什么样（target_metadata = Base.metadata）
# 配好一次后，以后基本不用再动它。

# 顶部 imports 区域，添加：
import sys, os
# 把【项目根目录】加进 sys.path，这样下面 import app.xxx 才找得到包。
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))   # 让项目根可 import / 将当前文件所在目录的父目录，临时添加到 Python 的模块搜索路径（sys.path）的最前面

from app.shared.db import Base
import app.shared.db.models   # 必须有，才会把模型注册进 Base.metadata
# 关键：必须 import 到 models.py，否则 SQLAlchemy 不知道你有 User/Conversation 表，
#       autogenerate 时也就没法帮你生成建表脚本。


from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.shared.db.config import ASYNC_DATABASE_URL


def _to_sync_url(url: str) -> str:
    """把异步驱动 URL 换成同步驱动。

    Alembic 的迁移执行是同步的（engine_from_config + connect），
    拿到 asyncpg / aiosqlite 这类异步驱动会直接报错，故需替换驱动：
      postgresql+asyncpg:// -> postgresql+psycopg://   （psycopg3 同步模式）
      sqlite+aiosqlite://   -> sqlite://
    两者指向同一个数据库，只是驱动不同。
    """
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        .replace("postgres+asyncpg://", "postgresql+psycopg://")
        .replace("sqlite+aiosqlite://", "sqlite://")
    )


def _strip_ssl_param(url: str) -> tuple[str, dict]:
    """从 URL 中剥离 ssl 参数，改为通过 connect_args 传递。

    为什么必须处理：asyncpg 接受 URL 里的 ?ssl=require，
    但 **psycopg 不接受**，会直接报
        invalid connection option "ssl"
    两边行为不一致，而 Alembic 走的正是 psycopg。
    故这里剥掉参数、改用 psycopg 的 sslmode 语义传参。
    """
    if "ssl=require" not in url and "sslmode=" not in url:
        return url, {}
    import re

    cleaned = re.sub(r"[?&]ssl=require", "", url)
    cleaned = re.sub(r"[?&]sslmode=[^&]*", "", cleaned)
    # 去掉可能残留的孤立 ? 或 &
    cleaned = re.sub(r"\?$", "", cleaned).replace("?&", "?")
    if cleaned.startswith("postgresql"):
        return cleaned, {"sslmode": "require"}
    return cleaned, {}


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 数据库地址以应用配置为准（环境变量 DATABASE_URL > .env > SQLite 回退），
# 而不是 alembic.ini 里写死的那个。否则改数据库要改两处、且容易不一致。
_SYNC_URL, _CONNECT_ARGS = _strip_ssl_param(_to_sync_url(ASYNC_DATABASE_URL))
config.set_main_option("sqlalchemy.url", _SYNC_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata
# ↑ 这一行最关键！告诉 Alembic“你的表结构真相在 Base.metadata 里”，
#   有了它，--autogenerate 才能对比“代码模型 vs 数据库”并生成迁移脚本。


# langgraph checkpointer 自管的表：由 AsyncPostgresSaver.setup() 创建，
# 不在 Base.metadata 里。若不过滤，autogenerate 会认为“库里有、模型里没有”，
# 进而生成**删除这些表**的迁移 —— 那会直接抹掉全部对话历史。
# 这里按名称前缀排除，让 Alembic 完全不参与它们的生命周期。
_MANAGED_TABLE_PREFIXES = ("checkpoint",)


def _include_name(name, type_, parent_names) -> bool:  # noqa: ANN001
    """autogenerate 的对象过滤器（表/索引级）。"""
    if type_ == "table" and name and name.startswith(_MANAGED_TABLE_PREFIXES):
        return False
    if type_ == "index" and name and name.startswith(_MANAGED_TABLE_PREFIXES):
        return False
    return True


def _include_object(obj, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    """对象级过滤：兜住 include_name 覆盖不到的反射对象。"""
    table = getattr(obj, "table", None)
    if table is not None and table.name.startswith(_MANAGED_TABLE_PREFIXES):
        return False
    if type_ == "table" and name and name.startswith(_MANAGED_TABLE_PREFIXES):
        return False
    return True


# 其他值：env.py 可以在运行时动态覆盖 alembic.ini 的配置（比如 url）。
# 这里默认用.ini里的 url，之后若想切 Postgres 也可在此覆盖。


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    离线模式：不真正连数据库，只“生成 SQL 字符串”输出。
    适合：在只有 schema 没有数据库连接的环境下预览将要执行的 SQL。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    在线模式：真正连数据库执行迁移（我们日常 upgrade 走的是这个）。
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # ssl 参数已从 URL 剥离，改由这里传给 psycopg
        connect_args=_CONNECT_ARGS,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # compare_type：列类型变化也参与 autogenerate 比对。
            # 迁移 SQLite（类型宽松）到 PostgreSQL（类型严格）时，
            # 不开启这个选项会漏掉类型差异，导致 alembic check 假通过。
            compare_type=True,
            compare_server_default=True,
            # 排除 langgraph 自管的 checkpoint 表，否则会被判定为「待删除」
            include_name=_include_name,
            include_object=_include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

