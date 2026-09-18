
<div align="center">

# 🌏 Voyage AI — 智能旅行规划平台

**基于 FastAPI + SQLAlchemy + LangChain/LangGraph 多 Agent 的 AI 旅行规划后端**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-2C3E50.svg)](https://www.sqlalchemy.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-FF6F00.svg)](https://www.langchain.com/)
[![Version](https://img.shields.io/badge/Version-v0.1.0-orange.svg)]()

**当前版本：`v0.1.0`（MVP 阶段）**

</div>

---

## 📌 项目简介

Voyage AI 是一个智能旅行规划平台后端，定位为「旅行专家 + 生活闲聊伙伴」。平台提供完整的用户体系、会话管理与基于多 Agent 协作的流式对话能力，可按需调用天气、车次票价、行程推荐等工具，生成个性化、可核验的出行方案，并通过会话状态持久化实现连续的多轮规划体验。

当前已完成**用户模块（含 Refresh Token 令牌闭环）、对话闭环与行程模块**，Redis 已接入（验证码 / 重置令牌 / Refresh Token 存储）。下一步聚焦 AI 能力调优（提示词、工具 skills）与安全/生产化加固（限流、监控、测试体系、数据库迁移）。

---

## 🏗️ 系统架构

```mermaid
flowchart TB
    subgraph FE["前端"]
        FE1["Web 应用"]
    end

    subgraph API["FastAPI 应用层"]
        CORE["核心组件<br/>统一响应 · 异常处理 · 业务错误码"]
        MOD["业务模块<br/>用户 · 会话 · AI 多 Agent · 行程"]
    end

    subgraph DATA["数据与外部服务"]
        DB[("业务数据库")]
        REDIS["Redis<br/>验证码 / 令牌"]
        LLM["大模型服务"]
        TOOLS["工具服务<br/>天气 / 车次 / 推荐"]
    end

    FE1 --> MOD
    MOD --> CORE
    MOD --> REDIS
    MOD --> LLM
    MOD --> TOOLS
    CORE --> DB
```


---

## ✨ 功能特性

> 标记规则：✅ 已实现 ｜ 🔄 半实现 ｜ ⬜ 未实现

### 👤 用户模块

| 功能 | 状态 |
|------|------|
| 用户注册（邮箱 + 安全密码哈希） | ✅ |
| 密码强度校验（注册与改密均生效） | ✅ |
| 用户登录（JWT 令牌认证） | ✅ |
| 请求鉴权（受保护接口令牌校验） | ✅ |
| 个人资料查看与修改（昵称、头像） | ✅ |
| 修改密码（校验当前密码与新旧一致性） | ✅ |
| 用户注销（清理会话后删除账号） | ✅ |
| 可选头像库 | ✅ |
| Refresh Token（签发 / 刷新 / 登出撤销 / 批量撤销） | ✅ |
| 邮箱验证码 / 两步密码重置 | ✅ |
| 软删除与注销冷却反悔机制 | ⬜ |

### 💬 会话与 AI 对话模块

| 功能 | 状态 |
|------|------|
| 会话创建与列表 | ✅ |
| 历史消息查询 | ✅ |
| 会话删除（含批量清理） | ✅ |
| 会话归属鉴权 | ✅ |
| SSE 流式对话响应 | ✅ |
| 多 Agent 协作编排 | ✅ |
| 工具调用（天气、车次、行程推荐等） | ✅ |
| 模型韧性（重试、降级、限流） | ✅ |
| 会话状态持久化 | ✅ |
| 会话状态清理的失败补偿与日志 | 🔄 |
| 长会话上下文压缩 | 🔄 |

### 🧳 行程模块

| 功能 | 状态 |
|------|------|
| 行程规划（生成 / 查询 / 编辑 / 删除） | ✅ |
| AI 结构化提取 | ✅ |

### 🗄️ 基础设施

| 功能 | 状态 |
|------|------|
| 异步数据库与 ORM 框架 | ✅ |
| 数据库迁移工具 | ✅ |
| 统一响应格式与业务错误码 | ✅ |
| 事务控制 | ✅ |
| Redis（验证码 / 重置令牌 / Refresh Token 存储） | ✅ |
| SQLite → PostgreSQL 迁移 | 🔄 |

---

## 🔍 核心流程

### AI 对话流式响应

```mermaid
sequenceDiagram
    autonumber
    participant C as 客户端
    participant S as 会话服务
    participant A as LangGraph Agent
    participant T as 工具 / 大模型

    C->>S: 发送消息
    S->>A: 流式调用 Agent
    loop 流式事件
        A->>T: 需要实时数据？
        T-->>A: 工具结果
        A-->>S: 内容 / 思考 / 工具结果
        S-->>C: SSE 分帧推送
    end
    A-->>S: 会话状态持久化
    S-->>C: 流结束标记
```

### 多 Agent 协作流程

```mermaid
flowchart LR
    REQ["用户请求"] --> DEC{"需要实时数据？"}
    DEC -->|是| TOOLS["工具调用<br/>天气 / 车次 / 推荐"]
    DEC -->|否| GEN["直接生成回答"]
    TOOLS --> OUT["组装行程方案"]
    GEN --> OUT
    OUT --> DONE["流式返回客户端"]
```

---

## 🗺️ 开发路线

```mermaid
gantt
    title Voyage AI 开发路线图
    dateFormat  YYYY-MM-DD

    section 用户模块
    认证与账号闭环        :done, p1, 2026-08-01, 7d

    section 对话闭环
    会话 + 多 Agent + 工具  :done, p2, 2026-08-08, 7d

    section 行程规划
    行程生成 / 查询 / 编辑  :done, p3, 2026-08-15, 21d

    section AI 能力调优
    提示词 / Skills 优化    :active, p4, 2026-09-19, 21d

    section 生产化
    Redis 令牌存储          :done, p5, 2026-09-05, 7d
    数据库迁移              :p5b, 2026-10-10, 14d
    限流 / 监控 / 安全加固  :p5c, 2026-10-10, 21d

    section 前端与测试
    前端对接 + 测试体系     :p6, 2026-10-24, 14d
```

---

## 🧩 模块说明

| 模块 | 描述 | 状态 |
|------|------|------|
| 用户模块 | 注册、登录、令牌认证、资料、改密、注销 | ✅ 稳定 |
| 会话模块 | 会话管理、流式对话、历史消息 | ✅ 稳定 |
| AI 模块 | 多 Agent 编排、工具调用、模型降级 | ✅ 可用 |
| 行程模块 | 生成、查询、编辑、删除、AI 结构化提取 | ✅ 稳定 |
| 业务框架 | 统一响应、错误码、异常处理 | ✅ 稳定 |
| 数据层 | 异步 ORM、事务控制、数据库迁移、Redis 令牌存储 | ✅ 稳定 |

---

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI · Uvicorn |
| ORM / 数据库 | SQLAlchemy · SQLite（未来迁移至 PostgreSQL） |
| 认证 | Argon2 密码哈希 · JWT 令牌 |
| 缓存 / 令牌 | Redis（redis-py asyncio） |
| 邮件服务 | Resend SMTP（aiosmtplib） |
| AI / Agent | LangChain · LangGraph |
| 模型接入 | DeepSeek / Qwen / GLM（多模型降级） |
| 流式传输 | SSE 服务端推送 |
| 工具链 | 天气 · 车次票价 · 行程推荐 · 日期 |
| 前端（规划） | Vue 3 · Element Plus |
| 工程 | uv · pytest（规划） |

---

## 📁 项目结构

```
voyage/
├── app/
│   ├── core/          # 框架核心（响应、异常、AI 编排）
│   ├── modules/       # 业务模块（用户 / 会话 / 行程）
│   └── shared/        # 公共组件（数据库、Redis、工具）
├── alembic/           # 数据库迁移
├── data/              # 运行时数据
├── tests/             # 测试
└── pyproject.toml     # 项目配置
```

---

## 🚀 快速开始

1. 安装依赖（Python ≥ 3.12 + uv）
2. 配置环境变量（数据库、密钥与模型 API Key）
3. 初始化数据库（`alembic upgrade head`）
4. 启动服务：`python run.py`
5. 访问接口文档（`/docs`）

> 详细步骤见项目文档；AI 对话功能需配置大模型 API Key。

### 数据库

主用 **PostgreSQL**，通过 `DATABASE_URL` 配置：

```
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname?ssl=require
```

**留空则回退到 SQLite**（`data/exports/app.db`），本地开发与单元测试不必先装 PG。

两个存储都指向同一个库：

| 存储 | 内容 | 驱动 |
|---|---|---|
| 业务表 | 用户、会话、行程、Token 用量、审计、记忆 | asyncpg（经 SQLAlchemy） |
| 会话消息状态 | langgraph checkpointer（历史消息的实体） | psycopg |

> ⚠️ **Windows 上必须用 `python run.py` 启动**，不要直接 `uvicorn app.main:app`。
> psycopg 的异步模式不接受 Windows 默认的 `ProactorEventLoop`，而 uvicorn 在
> Windows 上会硬编码返回它（连 `--loop asyncio` 都不理会）。
> `run.py` 显式指定了 `SelectorEventLoop`；Linux/macOS 无此问题。

### 创建管理员

系统不提供「第一个注册用户自动成为管理员」——那是真实的提权漏洞。
管理员必须由掌握服务器权限的人显式执行：

```bash
# 密码走环境变量，不进 shell 历史
ADMIN_PASSWORD='你的强密码' python app/scripts/create_admin.py \
  --email you@example.com --username 你的昵称 --password-env ADMIN_PASSWORD
```

---

## 🐳 Docker 部署

已提供完整容器化配置，一条命令拉起 Redis + 后端 + 前端：

```bash
cp .env.example .env      # 填入真实密钥（数据库、模型 API Key、JWT、邮件等）
docker compose up -d --build
```

> **数据库不在 compose 里**：默认连 `DATABASE_URL` 指向的外部 PostgreSQL
> （如 Neon / 自建实例）。若要用容器内 PG，自行在 compose 中加一个
> `postgres:16-alpine` 服务并把 `DATABASE_URL` 指向它。
> 不配 `DATABASE_URL` 时后端会回退到容器内 SQLite（`/app/data` 卷），
> 适合单机演示，但不适合多人使用。

启动后访问 `http://<服务器地址>/`（默认 80 端口，可用 `WEB_PORT=8080` 覆盖）。

### 服务构成

| 服务 | 镜像 | 说明 |
|---|---|---|
| `redis` | `redis:7-alpine` | 限流、验证码、Refresh Token、Token 用量统计 |
| `backend` | 本地构建 | FastAPI，**启动时自动执行 `alembic upgrade head`** |
| `web` | 本地构建 | nginx 托管前端，并把 `/api` 反代到 backend |

只有 `web` 对外暴露端口；后端与 Redis 仅在内网可达，浏览器只看到一个源，
因此**无需配置 CORS**。

### ⚠️ 部署前必须改的两项

1. **`SHARE_BASE_URL`** —— 分享链接的对外基址。默认是 `http://localhost`，
   不改的话复制出来的分享链接别人打不开：
   ```bash
   SHARE_BASE_URL=https://your-domain.com docker compose up -d
   ```

2. **数据持久化** —— SQLite（`app.db` + `checkpoints.sqlite`）与日志通过
   `./data:/app/data` 挂载到宿主机。**这个目录就是全部业务数据**，
   升级重建容器不会丢，但请自行纳入备份。

### 常用操作

```bash
docker compose logs -f backend      # 跟踪后端日志
docker compose restart backend      # 重启后端
docker compose down                 # 停止（保留数据卷）
docker compose up -d --build        # 更新代码后重新部署（会自动跑迁移）
```

在容器内执行管理脚本（如创建管理员）：

```bash
docker compose exec backend python app/scripts/create_admin.py \
  --email you@example.com --username 你的昵称
```

### 关于 Redis 版本

必须使用 **Redis ≥ 7**。限流的计数原语依赖 `EXPIRE` 的 `NX` 选项
（7.0 才引入）；当前实现已改用 Lua 脚本以兼容 5.x/6.x，
但 7.x 才有完整的过期语义。

### 不使用 Docker 时

`Dockerfile` 是标准的单镜像构建，也可单独使用：

```bash
docker build -t voyage-backend .        # 后端（上下文为仓库根）
docker build -f web/Dockerfile -t voyage-web ./web   # 前端（上下文为 web/）
```

构建上下文与 `.dockerignore` 已配置妥当：`.env`（密钥）与 `data/`（本机数据）
都会被排除，不会进镜像层。

---

## 📋 开发计划

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 用户模块 + 令牌认证 | ✅ 已完成 |
| Phase 2 | 会话管理 + AI 流式对话 | ✅ 已完成 |
| Phase 3 | 行程规划（生成 / 编辑 / 删除 / 结构化提取） | ✅ 已完成 |
| Phase 4 | AI 能力调优（提示词 / Skills） | 🔄 进行中 |
| Phase 5 | 生产化：限流 / 监控 / 安全加固 / 数据库迁移 | 🔄 进行中 |
| Phase 6 | 前端对接 + 测试体系 | ⬜ 待开发 |

---

<div align="center">

*Voyage AI · v0.1.0 · 持续迭代中*

</div>