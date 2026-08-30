from contextlib import asynccontextmanager
from fastapi.responses import RedirectResponse
from fastapi import FastAPI
from app.core.ai import AgentFactory
from app.core.business import register_exception
from app.api import api_router
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from app.shared.utils import init_log, close_log
from app.shared.redis import redis_client
SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "exports" / "checkpoints.sqlite"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_log()
    try:
        await redis_client.init_redis()
        async with AsyncSqliteSaver.from_conn_string(str(SQLITE_PATH)) as checkpointer:
            AgentFactory.initialize(checkpointer)
            try:
                yield
            finally:
                AgentFactory.reset()   # 异常也兜底，且仍在连接关闭前
    finally:
        await redis_client.close()
        close_log()
    
app = FastAPI(title="voyage Plan Assistant",lifespan=lifespan)

app.include_router(api_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception(app)
@app.get("/")
def read_root():
    return RedirectResponse(url="/docs")


# ==============================================================
# TODO / 项目演进计划
# （[x]=已完成 [~]=部分完成 [ ]=待办；按优先级排序）
# ==============================================================
#
# ─────────── 阶段 1：功能闭环收尾 ─────────────────────────────
# [~] 1. 会话删除的一致性
#     - 已实现：先删业务行（事务内）再清 checkpoint，失败残留记录于日志
#     - 待补：孤立 checkpoint 清理函数（扫描无对应会话行的残留数据并删除）
#
# ─────────── 阶段 2：扩展与生产化 ─────────────────────────────
# [ ] 2. AI 能力调优（建议下一个开发方向）
#     - 提示词工程：监督提示词、工具描述、结构化提取提示词，建立版本管理与评测口径
#       （工具命中率、结构校验通过率等）
#     - 工具 skills 打磨：中文化描述 + 触发示例，提升 agent 工具选择准确率
#     - MCP：现有接入查缺补漏，评估工具服务化与第三方 MCP 扩展
#     - 可选：模型参数（温度等）与多模型路由 / 降级策略调优
# [~] 3. 令牌与注销
#     - 用户注销已完成（会话清理 + 账号删除，未引入软删除）
#     - refresh token 半实现，待接入 Redis 后启用
#     - 邮箱验证码 / 忘记密码未实现（需 SMTP 服务，答辩演示需提前准备，如 Resend）
#        -- 登录时直接给邮箱发验证码，前端携带邮箱账号、验证码、密码进行登录
#        -- 重置密码采用两步验证：验证码换临时 token，再凭临时 token 重置密码
#     - 可选：会话短期记忆迁移至 Redis checkpointer（已有暂存方案）
# [ ] 4. SQLite 统一迁移到 PostgreSQL（asyncpg + sqlalchemy，配合 Alembic）
#     - 当前无强需求,建议放在最后
# [~] 5. 生产化：日志、监控、限流、错误告警
#     - 模型层重试 / 降级 / 限流已完成，日志系统暂缓
# ==============================================================
