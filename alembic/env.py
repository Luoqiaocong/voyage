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

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

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
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

