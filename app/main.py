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
# ─────────── 阶段 1：功能闭环（已完成）────────────────────────
# [x] 1. 认证与令牌闭环
#     - 邮箱验证码（Resend SMTP）签发与一次性消费
#     - 两步密码重置：验证码 → 重置令牌 → 更新密码（提交后消费令牌）
#     - Refresh Token 生命周期：Redis 哈希落库 / 多设备集合 /
#       单点登出撤销 / 改密、重置、注销批量撤销 / 刷新换发接口
#     - 用户模块健壮性：密码哈希容错、注册校验顺序、并发唯一约束兜底
# [x] 2. 会话删除一致性（先删业务行再清 checkpoint，失败残留记日志）
# [x] 3. 错误处理可观测性（未捕获异常堆栈 / 工具失败信息收敛）
#
# ─────────── 阶段 2：已知短板（建议优先处理）──────────────────
# [~] 4. AI 能力调优
#     - 提示词工程：监督提示词、工具描述、结构化提取提示词，建立版本管理与评测口径
#       （工具命中率、结构校验通过率等）
#     - 工具 skills 打磨：中文化描述 + 触发示例，提升 agent 工具选择准确率
#     - MCP：现有接入查缺补漏，评估工具服务化与第三方 MCP 扩展
# [~] 5. 安全与健壮性加固
#     - 账号禁用位（is_active）与登录 / 刷新 / 鉴权联动（错误码已预留）
#     - 验证码 / 登录频率限制（RATE_LIMIT_EXCEEDED 已预留）
#     - 历史消息接口收敛返回字段（避免工具入参透传）并提供分页
#     - CORS 生产白名单（当前仅限开发）、邮件发送重试
# [~] 6. 生产化：日志、监控、限流、错误告警
#     - 模型层重试 / 降级 / 限流已完成；待接入错误告警与请求追踪
#
# ─────────── 阶段 3：架构演进（低优先级）─────────────────────
# [ ] 7. SQLite → PostgreSQL（asyncpg + SQLAlchemy + Alembic）
#     - 当前无强需求，建议放在最后；会话持久化一并评估 Redis / PG 方案
# [ ] 8. redis-py 升级 8.x（修复 srem/smembers 类型标注问题）
#     - 当前被 redisvl 的 redis<8.0 约束阻塞，需配合 redisvl 解禁后升级
# [ ] 9. 用户长期记忆（MVP：结构化画像提取 + 新会话注入；语义存储后置）
#     - 优先级低于阶段 2；以"记住用户偏好"为最小闭环，不引入向量库
# ==============================================================

# 会话状态持久化（langgraph checkpoint）当前为 SQLite，迁移方案见上方演进计划 #7

