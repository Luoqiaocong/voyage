"""数据库连接配置：URL、连接池参数。"""
from pathlib import Path

# ---- 数据库文件位置 ----
# 和你的 checkpoints.sqlite 放一起，方便管理
DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "exports" / "app.db"
# ── 这句逐层拆解 ────────────────────────────────────────────────
# __file__          : 当前文件(config.py)的路径
# .resolve()        : 转成绝对路径
# .parent           : 上一级目录。config.py 在 app/shared/db/ 下，
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
DB_POOL_CONFIG = dict(
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
