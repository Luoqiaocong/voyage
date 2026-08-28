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
# （按优先级分阶段，随开发推进勾选；[x]=已完成 [~]=部分完成 [ ]=待办）
# ==============================================================
#
# ─────────── 阶段 1：功能闭环（核心业务先跑通） ───────────────
# [x] 1. 实现 itineraries 行程模块
#     - 生成行程 → 持久化 → 查看/编辑/删除 → 与 conversation/用户绑定
#     - AI 结构化提取（json_mode）已落地，行程归属鉴权统一 60001
# [x] 2. 会话标题功能：按对话内容自动生成 + 手动修改
#     - 自动生成只在首个对话后触发，失败不影响流式主流程
# [x] 3. 会话创建频率控制：同一用户在一段时间内只保留一个空会话
#     - 防止“创建会话”被无限调用堆积无内容会话
#     - 已有空会话时复用或拒绝并返回业务提示（策略：时间窗口 or 空会话检测，待定）
# [ ] 4. 多会话批量删除：支持一次删除多个会话
#     - 逐个先清 checkpoint 再删库；注意存在性/归属校验与部分失败处理
# [~] 5. 会话删除的一致性
#     - 先删 memory(thread) 再删 DB，一端失败时的补偿机制待补
# [x] 6. knowledge / RAG 模块 —— 已搁置（不开发 RAG，精力转向 AI 能力调优，见 #19）
#
# ─────────── 阶段 2：质量与健壮性 ─────────────────────────────
# [x] 7. 参数统一用 Annotated 配置（类型安全）
#     - 已覆盖 user / conversation / itinerary 的 schema、依赖与路由
# [x] 8. 增加函数 docstring（功能 + 参数类型声明）—— 主体已覆盖，遗漏随手补
# [x] 9. 时间统一：UTC 存储、上海时区展示，会话/行程响应一致
# [x] 10. 流式对话健壮性：中途异常返回 error 事件，不再悬挂连接
# [x] 11. 分层修正：事务组件不再反向依赖业务异常，AI 工具目录语义统一
# [x] 12. 行程响应容错：来源会话删除后不再报错
# [x] 13. token 解析确认：FastAPI 依赖缓存保证同一请求只解析一次
# [ ] 14. 自动化测试（至少：鉴权、会话 CRUD 的核心路径），替换早期会挂的测试
# [ ] 15. 前端（Streamlit）与后端鉴权对接 + 会话恢复到后端持久化
# [x] 16. 对 .env.example 补齐新增配置（JWT、HASH 等）—— 当前文件为空，需优先补齐
# [ ] 17. 清理遗留：test、data 等不需要的目录/文件
#
# ─────────── 阶段 3：扩展与生产化 ─────────────────────────────
# [ ] 18. SQLite 统一迁移到 PostgreSQL（asyncpg + sqlalchemy，配合 Alembic）
# [ ] 19. AI 能力调优（下一个开发方向）
#     - 提示词工程：监督提示词、工具描述、结构化提取提示词，建立版本管理与评测口径
#       （工具命中率、结构校验通过率等）
#     - 工具 skills 打磨：中文化描述 + 触发示例，提升 agent 工具选择准确率
#     - MCP：评估用 FastMCP 将旅行工具服务化，经 LangChain MCP 适配器接入（或第三方 MCP）
#     - 可选：模型参数（温度等）与多模型路由 / 降级策略调优
# [~] 20. 令牌与注销
#     - 用户注销已完成（会话清理 + 账号删除，未引入软删除）
#     - refresh token 半实现，待接入 Redis 后启用
#     - 邮箱验证码 / 忘记密码未实现（需 SMTP 服务，答辩演示需提前准备，如 Resend）
#        -- 登录时直接给邮箱发验证码，前端携带邮箱账号、验证码、密码进行登录
#        -- 重置密码采用两步验证，第一步携带验证码请求后端返回临时token，第二步携带临时token请求后端重置密码
# [x] 21. 用户信息管理（改密、改昵称、头像固定方案）—— 已完成
# [~] 22. 生产化：日志、监控、限流、错误告警
#     - 模型层重试 / 降级 / 限流已完成，其余暂缓（日志系统先不做）
# ==============================================================
