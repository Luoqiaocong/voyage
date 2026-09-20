"""应用入口。

注意开头的 Windows 事件循环处理：会话状态由 langgraph 的 psycopg
checkpointer 持久化，而 psycopg 的异步模式**拒绝 ProactorEventLoop**
（Windows 上 asyncio 的默认实现）。
这里的设置是对启动方式的兜底——推荐仍用仓库根目录的 run.py 启动。
"""
import asyncio
import sys
import time

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi.responses import RedirectResponse
from fastapi import FastAPI
from app.core.ai import AgentFactory
from app.core.ai.llm import close_http_client
from app.core.business import register_exception
from app.api import api_router
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from app.shared.utils import close_log, init_log, log
from app.config import config
from app.shared.db.checkpoint import open_checkpointer
from app.shared.redis import redis_client
from app.shared.flush_task import usage_flush_task
from app.shared.memory_task import memory_extract_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_log()
    try:
        await redis_client.init_redis()
        # checkpointer 按数据库后端自动选择 PG / SQLite（见 shared/db/checkpoint.py）
        async with open_checkpointer() as checkpointer:
            AgentFactory.initialize(checkpointer)
            usage_flush_task.start()   # 周期性把 Token 增量落库
            # 后台预热：把首次调用的建连开销从「用户等待」挪到「启动时」。
            # 不 await —— 预热失败或慢都不该拖住服务就绪，
            # 真正需要时仍会按需惰性构建（见 agents/travel.py）。
            prewarm_task = asyncio.create_task(_prewarm())
            try:
                yield
            finally:
                prewarm_task.cancel()
                AgentFactory.reset()   # 异常也兜底，且仍在连接关闭前
    finally:
        # 退出前收尾：先等记忆提炼（它用的是独立 DB 会话），再落库、关连接
        await memory_extract_task.stop()
        await usage_flush_task.stop()
        await close_http_client()   # 释放共享 LLM 连接池
        await redis_client.close()
        close_log()


async def _prewarm() -> None:
    """预热重资源，缩短用户第一次提问的等待。

    为什么需要：首次调用 travel_recommend 耗时约 120 秒（含 MCP 建连与
    8 个网络工具的准备）。这段开销与用户的具体问题无关，完全可以提前付掉
    ——启动时多花几秒，换来用户侧少等。

    刻意做成「尽力而为」：任一步失败只记日志，不影响服务可用性，
    因为所有资源在真正用到时都会惰性重建。
    """
    try:
        from app.core.ai.mcp import get_namespace_tools

        t0 = time.perf_counter()
        # 主 Agent 的工具本身就注册在启动路径上，这里补的是 travel 子 Agent。
        # 只取工具（会建立 MCP 连接），不构建 agent —— 构建要等模型，
        # 而模型调用无法复用，预热它没有意义。
        tools = await get_namespace_tools("travel")
        log.info(
            f"[prewarm] travel 工具已就绪（{len(tools)} 个），"
            f"耗时 {time.perf_counter() - t0:.2f}s"
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning(f"[prewarm] 失败，将在首次调用时按需构建: {type(exc).__name__}: {exc}")


app = FastAPI(title="voyage Plan Assistant",lifespan=lifespan)

app.include_router(api_router)


app.add_middleware(
    CORSMiddleware,
    # 默认允许所有来源（开发便利）；配置了 ALLOWED_ORIGINS 就按白名单收窄。
    # 同源部署（nginx 把 /api 反代到后端）时浏览器不会发跨域请求，无需配置此项。
    allow_origins=config.ALLOWED_ORIGINS or ["*"],
    # 刻意**不设** allow_credentials。
    #
    # 原因：本系统用 Authorization: Bearer 头传令牌，前端既没开
    # withCredentials、后端也不依赖 Cookie —— 没有任何需要「携带凭据」的场景。
    # 而 allow_credentials=True 与 allow_origins=["*"] 是浏览器规范**禁止的组合**，
    # 将来一旦发出带凭据的跨域请求会被浏览器直接拒绝，且报错难以定位。
    # 保持默认 False 更安全。
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
#     - 验证码 / 登录 / 注册 / 重置接口限流 ✅ 已实现（IP + 邮箱维度，Redis 固定窗口 + 429）
#     - 已取消：账号禁用位（is_active）（产品决策：暂不需要）
#     - 历史消息接口收敛返回字段（避免工具入参透传）并提供分页
#     - CORS 生产白名单（当前仅限开发）、邮件发送重试
# [~] 6. 生产化：日志、监控、限流、错误告警
#     - 模型层重试 / 降级 / 限流已完成；待接入错误告警与请求追踪
#
# ─────────── 阶段 3：架构演进（低优先级）─────────────────────
# [ ] 7. SQLite → PostgreSQL（asyncpg + SQLAlchemy + Alembic）
#     - 当前无强需求，建议放在最后；会话持久化一并评估 Redis / PG 方案
# [ ] 8. 用户长期记忆（MVP：结构化画像提取 + 新会话注入；语义存储后置）
#     - 优先级低于阶段 2；以"记住用户偏好"为最小闭环，不引入向量库
# ==============================================================

# 会话状态持久化（langgraph checkpoint）当前为 SQLite，迁移方案见上方演进计划 #7

