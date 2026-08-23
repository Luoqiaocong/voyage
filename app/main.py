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
# （按优先级分阶段，随开发推进勾选；部分来自你已有的思路）
# ==============================================================
#
# ─────────── 阶段 1：功能闭环（核心业务先跑通） ───────────────
# 1. 实现 itineraries 行程模块（当前为空壳）
#    - 生成行程 → 持久化 → 查看/删除 → 与 conversation/用户绑定
# 2. 会话删除的一致性
#    - delete_conversation：先删 memory(thread) 再删 DB，失败需补偿
#      （避免“内存删了 / DB 没删”或反向的不一致）
# 3. knowledge / RAG 模块实现（等内容/场景明确后再动，见阶段 3）
#
# ─────────── 阶段 2：质量与健壮性 ─────────────────────────────
# 4. 参数统一用 Annotated 配置（类型安全），如 converter 里的 ConversationId
# 5. 增加函数 docstring（功能 + 参数类型声明）
# 6. 自动化测试（至少：鉴权、会话 CRUD 的核心路径），替换早期会挂的测试
# 7. get_current_user 在 cbv 中同一个请求被重复解析 token → 优化复用
# 8. created_at 存储格式收敛（去掉 .000000 的日期时间显示，未决方案待定）
# 9. 前端（Streamlit）与后端鉴权对接 + 会话恢复到后端持久化
# 10. 清理遗留：test、data 等不需要的目录/文件
# 11. 对 .env.example 补齐新增配置（JWT、HASH 等）
#
# ─────────── 阶段 3：扩展与生产化 ─────────────────────────────
# 12. SQLite 统一迁移到 PostgreSQL（asyncpg + sqlalchemy，配合 Alembic）
# 13. RAG：接入私有旅行攻略（需明确知识场景/语料来源后再实现）
# 14. refresh token 真正实现、用户密码重置场景【发送邮箱验证码】（需引入 Redis）+ 用户注销（会话checkpointer与数据库双重注销，但可能会引入软删除机制）
# 15. 用户信息管理（改密、改昵称、头像固定方案）
# 16. 生产化：日志、监控、限流、错误告警
# ==============================================================
