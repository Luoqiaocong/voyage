from contextlib import asynccontextmanager
from fastapi.responses import RedirectResponse
from langgraph.checkpoint.memory import InMemorySaver
from fastapi import FastAPI
from app.core.ai import AgentFactory
from app.core.business import register_exception
from app.api import api_router
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware

SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "exports" / "checkpoints.sqlite"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string(str(SQLITE_PATH)) as checkpointer:
        # 若 API 需要：await checkpointer.setup()
        # AgentFactory.initialize()
        AgentFactory.initialize(checkpointer)
        # app.state.checkpointer = checkpointer  # 可选：事后读 state 用
        yield
    AgentFactory.reset()  # 关闭前清掉，避免指着已关连接
    
app = FastAPI(title="VOYAGE AI TRAVEL PLANNER",lifespan=lifespan)

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
#     - 先删 memory(thread) 再删 DB，一端失败时的补偿机制待补
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
#     - 当前无强需求（RAG 已搁置、无向量场景），建议放在最后
# [~] 5. 生产化：日志、监控、限流、错误告警
#     - 模型层重试 / 降级 / 限流已完成，日志系统暂缓
# [ ] 6. 清理遗留：test、data 等不需要的目录/文件
# ==============================================================
