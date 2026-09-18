# ============================================================================
# Voyage 后端镜像（多阶段构建）
#
# 构建上下文是**仓库根目录**（不是 app/），因为镜像里要保持项目原有的目录结构：
# 应用的 SQLite 与日志路径都相对于项目根解析——
#   data/exports/app.db、data/exports/checkpoints.sqlite、data/output/logs/
# 打乱层级会导致数据被写进镜像层（重启即丢）。
#
#   docker build -f Dockerfile -t voyage-backend .
#
# 前端由 web/Dockerfile 单独构建（nginx 托管并把 /api 反代到这里），
# 故本镜像不含前端产物——避免同一个前端在两个镜像里各构建一遍。
# ============================================================================

# ---------- 阶段 1：Python 依赖 ----------
FROM python:3.12-slim-bookworm AS builder

# 直接取 uv 官方镜像里的静态二进制，比 pip install uv 更快、版本也更可复现
COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# pyproject.toml 里已配置阿里云 PyPI 镜像，无需在此额外指定 index。
# 先只拷清单文件：依赖不变时这一层能命中缓存，改业务代码不必重装依赖。
# --no-install-project：本项目自身不是要安装的包，只需它的依赖。
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


# ---------- 阶段 2：运行时 ----------
FROM python:3.12-slim-bookworm AS runtime

# curl 供 HEALTHCHECK 使用；
# tini 负责正确转发信号——uvicorn 需要收到 SIGTERM 才会优雅关闭，
# 否则容器停止时 app 的 lifespan 收尾逻辑（落库、关连接）来不及执行。
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# 非 root 运行：容器被攻破时限制影响面
RUN useradd --create-home --shell /bin/bash --uid 10001 voyage

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
# 应用代码、迁移脚本与配置
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini pyproject.toml uv.lock .env.example ./
# run.py 是仓库约定的启动入口（内含事件循环处理），一并打包。
# Linux 下 CMD 直接用 uvicorn 即可（默认就是 SelectorEventLoop），
# 带上它可保证容器内外启动方式一致，也便于进容器手动排查。
COPY run.py ./

# 日志目录必须先建好并授权给非 root 用户。
# 注意：这里同时建 data/exports 是为了兼容「不配 DATABASE_URL 时回退 SQLite」
# 的用法；配了 PostgreSQL 时业务数据不在容器里，该目录只放日志。
RUN mkdir -p /app/data/exports /app/data/output/logs \
    && chown -R voyage:voyage /app

USER voyage

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8000

# 复用已有的 /docs，无需为此新增端点。
# start-period 留足时间给数据库迁移与 Redis 建连。
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/docs || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# 先执行数据库迁移再启动服务：新部署或代码升级后表结构自动就绪。
# 只做 upgrade 不做 downgrade——避免误操作回退掉线上数据。
#
# 关于直接用 uvicorn 而不经 run.py：
# 迁移到 PostgreSQL 后会话状态由 psycopg checkpointer 持久化，而 psycopg
# 异步模式不接受 ProactorEventLoop——Windows 上必须用 run.py 显式指定
# SelectorEventLoop。但**本镜像是 Linux，默认就是 SelectorEventLoop**，
# 故此处直接 uvicorn 即可，无需 run.py。（run.py 仍打进镜像以便一致启动。）
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
