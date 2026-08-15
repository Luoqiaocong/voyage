# Voyage 项目架构指南

## 项目概述

Voyage 是一个 AI 旅行规划助手后端，基于 **FastAPI + LangGraph + LlamaIndex** 构建，支持多模型 LLM 调用、SSE 流式对话、RAG 知识检索。当前处于 **MVP 阶段**，Chat 模块已跑通，其余模块（Auth、Itineraries、Knowledge）为 Stub 状态。

---

## 技术栈

| 层级 | 技术 | 版本 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | >=0.141.1 |
| AI Agent | LangChain + LangGraph | >=1.3.14 |
| RAG 引擎 | LlamaIndex | >=0.14.23 |
| 向量数据库 | Milvus (pymilvus) | >=2.6.17 |
| 对象存储/缓存 | Redis | >=5.2.1 |
| ORM | SQLAlchemy (asyncio) | >=2.0.51 |
| 校验/配置 | Pydantic v2 + pydantic-settings | >=2.15.0 |
| SSE | sse-starlette | >=2.2.1 |
| 包管理 | uv | - |
| Python | 3.12 | - |

---

## 目录结构（当前实际）

```
voyage/
│
├── app/                              # ──── 应用主代码 ────
│   ├── main.py                       # FastAPI 应用入口 + Lifespan 管理
│   ├── config.py                     # VoyageConfig (BaseSettings) — 全量配置从 .env 加载
│   │
│   ├── core/                         # 核心基础设施
│   │   ├── route.py                  # UnifiedRoute — 自动包装统一响应体
│   │   ├── ai/                       # AI 引擎层
│   │   │   ├── agent.py              # AgentFactory (单例, LangGraph StateGraph)
│   │   │   ├── llm.py               # get_llm() 多模型工厂 (DeepSeek/Dashscope)
│   │   │   ├── memory.py            # 【空】Redis 短期记忆占位
│   │   │   └── middleware.py        # 【空】Token 审计占位
│   │   ├── business/                 # 业务错误码 + 异常体系
│   │   │   ├── code.py              # BusinessCode 枚举 (60+ 错误码, 6 域)
│   │   │   ├── exception.py         # 6 个领域异常类
│   │   │   └── util.py             # success_response() 统一响应包装
│   │   └── tools/                    # 【空】Agent 工具占位
│   │
│   ├── modules/                      # 功能模块（垂直切片）
│   │   ├── auth/                     # 鉴权模块 (Stub)
│   │   │   ├── router.py            # POST /auth/login
│   │   │   ├── service.py           # 返回 hardcoded fake-token
│   │   │   ├── models.py            # 【空】
│   │   │   └── schemas.py          # AuthRequest, AuthResponse
│   │   ├── chat/                     # 对话模块 (✅ 已实现)
│   │   │   ├── router.py            # GET/POST sessions + POST completions (SSE)
│   │   │   ├── service.py           # ChatService 委托 ChatFactory
│   │   │   ├── factory.py           # ChatFactory — astream_chat + get_messages
│   │   │   ├── schemas.py          # ChatRequest, SessionResponse
│   │   │   └── agents/             # 【空】Chat 专属 Agent 占位
│   │   ├── itineraries/             # 行程规划模块 (Stub)
│   │   │   ├── router.py            # POST /generate
│   │   │   ├── service.py           # 返回占位字符串
│   │   │   ├── models.py            # 【空】
│   │   │   └── schemas.py          # ItineraryRequest, ItineraryResponse
│   │   └── knowledge/               # 知识库模块 (Stub)
│   │       ├── router.py            # POST /query + /upload
│   │       ├── service.py           # 返回占位字符串
│   │       ├── rag_engine.py        # 【空】LlamaIndex RAG 占位
│   │       └── schemas.py          # KnowledgeQueryRequest, KnowledgeQueryResponse
│   │
│   └── shared/                       # 跨模块共享
│       ├── db/                       # 【空】SQLAlchemy Session 工厂占位
│       └── utils/
│           └── gen_sessid.py        # get_id() 生成 sess_{uuid} 会话 ID
│
├── data/                             # ──── 运行时数据 (.gitignore) ────
│   ├── docs/                         # 项目文档
│   │   ├── project-architecture-guide.md
│   │   ├── Voyage-AI-Travel-Planner-PRD.md
│   │   └── redis短期记忆方案.md
│   ├── exports/
│   │   └── checkpoints.sqlite       # LangGraph 对话状态持久化
│   └── output/
│       └── conversations_messages.json
│
├── tests/                            # ──── 测试 ────
│   └── test_supervisor_agent.py      # 单一异步测试
│
├── scripts/                          # 【空】运维脚本占位
│
├── .env                              # 本地环境变量 (gitignored)
├── .env.example                      # 【空】环境变量模板
├── .python-version                   # 3.12
├── pyproject.toml                    # 项目元数据 + 依赖
├── uv.lock                           # uv 锁文件
├── README.md                         # 项目说明
└── voyage.egg-info/                  # Editable install 元数据
```

---

## API 端点一览

所有端点挂载在 `/api/v1` 前缀下。

| 方法 | 路径 | 模块 | 状态 | 说明 |
|---|---|---|---|---|
| `POST` | `/auth/login` | auth | Stub | 返回 fake-token |
| `POST` | `/chat/sessions` | chat | ✅ | 创建会话，返回 session_id |
| `GET` | `/chat/sessions/{session_id}` | chat | ✅ | 获取会话历史消息 |
| `POST` | `/chat/completions` | chat | ✅ | SSE 流式对话 |
| `POST` | `/itineraries/generate` | itineraries | Stub | 占位响应 |
| `POST` | `/knowledge/query` | knowledge | Stub | 占位响应 |
| `POST` | `/knowledge/upload` | knowledge | Stub | 未实现 |
| `GET` | `/` | main | ✅ | 健康检查 |

---

## 核心架构详解

### 1. 应用入口 — `app/main.py`

```
FastAPI(lifespan=...)
  ├── lifespan 内: AsyncSqliteSaver 初始化 → AgentFactory.initialize(checkpointer)
  ├── 挂载 4 个 Router (auth, chat, itineraries, knowledge) → /api/v1
  └── 根路由 GET / → 健康检查
```

**Lifespan 流程：** 启动时创建 SQLite checkpointer → 初始化 AgentFactory 单例 → yield → 关闭时 reset AgentFactory。

### 2. 统一响应框架 — `core/route.py` + `core/business/`

**UnifiedRoute(APIRoute)** 拦截所有使用它的路由：
1. 判断响应是否 `JSONResponse`
2. 若响应体不含 `businsess_code` 键，自动用 `success_response()` 包装
3. 根据 HTTP 状态码映射到 `BusinessCode` 枚举
4. 流式响应 (SSE) 直接放行，不拦截

**响应格式：**
```json
{
  "code": 20000,
  "message": "success",
  "data": { ... }
}
```

**BusinessCode 枚举** 覆盖 6 个域：
- `1xxxx` — 通用/鉴权错误 (参数、令牌、限流等)
- `2xxxx` — 用户模块
- `3xxxx` — 会话与记忆模块
- `4xxxx` — AI Agent 与大模型模块
- `5xxxx` — 知识库与 RAG 模块
- `6xxxx` — 行程规划模块

**异常体系：** 6 个领域异常类继承 `BaseBusinessException`：`AuthException`, `UserException`, `SessionException`, `AgentException`, `KnowledgeException`, `ItineraryException`。

### 3. AI 引擎层 — `core/ai/`

#### LLM 工厂 — `llm.py`

`get_llm()` 根据模型名自动推断 Provider：

| 模型枚举 | Provider | 默认 Base URL |
|---|---|---|
| `deepseek-v4-flash` | DeepSeek | DEEPSEEK_BASE_URL |
| `deepseek-v4-pro` | DeepSeek | DEEPSEEK_BASE_URL |
| `qwen3.5-flash` (默认) | Dashscope | DASHSCOPE_BASE_URL |
| `qwen-max` | Dashscope | DASHSCOPE_BASE_URL |
| `glm-5` | Dashscope | DASHSCOPE_BASE_URL |

- 使用 `init_chat_model()` 统一初始化
- 默认 `temperature=1.4`，关闭 thinking 模式 (`enable_thinking: False`)

#### Agent 工厂 — `agent.py`

`AgentFactory` 单例模式：
- `initialize(checkpointer)` — 用 `create_agent()` 创建编译后的 StateGraph
- `get_agent()` — 获取已初始化的 Agent 实例
- `get_checkpointer()` — 获取 checkpointer 实例
- `reset()` — 清理（关闭时调用）

当前状态：空 tools 列表 + 通用 system prompt（"You are a helpful assistant"）。

### 4. Chat 模块 — `modules/chat/`（已实现）

**数据流：**
```
Client SSE ← router.py (yield ServerSentEvent)
           ← service.py (委托 ChatFactory)
           ← factory.py (astream_chat / get_messages)
           ← agent.py (AgentFactory.get_agent().astream())
           ← llm.py (get_llm() → init_chat_model)
```

**ChatFactory 核心方法：**
- `astream_chat(message, session_id)` — 通过 `agent.astream()` 流式输出 token
- `get_messages(session_id)` — 从 checkpointer 读取状态，转为 OpenAI 消息格式

**会话管理：**
- Session ID 格式: `sess_{uuid_hex_12}`
- 每个 session 对应 LangGraph 的一个 `thread_id`
- 对话状态持久化在 SQLite checkpointer 中

---

## 配置体系 — `app/config.py`

`VoyageConfig(BaseSettings)` 从 `.env` 加载全部配置：

```python
# API Keys
DASHSCOPE_API_KEY / DASHSCOPE_BASE_URL    # 阿里云 Dashscope
DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL     # DeepSeek
ALIYUN_BASE_URL                           # 阿里云通用
TAVILY_API_KEY                            # Tavily 搜索

# 模型名称
MULTIMODAL_EMBEDDING_MODEL / TEXT_EMBEDDING_MODEL
ALIYUN_LLM_MODEL / DEEPSEEK_LLM_MODEL_FLASH / DEEPSEEK_LLM_MODEL_PRO
RERANK_MODEL

# RAG 参数
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200
TOP_K = 10
RERANK_TOP_N = 5
```

---

## 依赖方向

```
modules/*/router.py  →  modules/*/service.py  →  core/ai/agent.py + core/ai/llm.py
                                            →  modules/*/factory.py (chat)
                                            →  modules/*/rag_engine.py (knowledge)

core/route.py  ←  所有使用 UnifiedRoute 的 Router
core/business/  ←  core/route.py + modules/* 异常处理
config.py  ←  core/ai/llm.py + 各模块 service
```

**禁止反向依赖：** `core/` 不得 import `modules/` 的任何东西。

---

## 文件放置原则

| 目录 | 放什么 | 不放什么 |
|---|---|---|
| `modules/*/router.py` | 路由定义、参数校验、调用 service | 业务逻辑、数据库查询、Agent 编排 |
| `modules/*/service.py` | 编排 db + agent + rag 的业务流程 | 路由装饰器、HTTP 请求/响应对象 |
| `modules/*/factory.py` | 模块核心执行逻辑 (如 ChatFactory) | 路由、HTTP 相关 |
| `modules/*/schemas.py` | Pydantic v2 请求/响应模型 | ORM 模型 |
| `modules/*/models.py` | SQLAlchemy ORM 模型 | 业务逻辑 |
| `core/ai/` | LLM 工厂、Agent 工厂、Agent 工具 | HTTP 路由、数据库操作 |
| `core/business/` | 错误码、异常类、响应包装 | 具体业务逻辑 |
| `core/route.py` | 全局响应拦截 | 业务逻辑 |
| `shared/utils/` | 纯函数工具 | 有状态逻辑 |
| `shared/db/` | SQLAlchemy session 工厂 | 业务查询 |

---

## 命名规则

| 类型 | 规则 | 示例 |
|---|---|---|
| 目录 | snake_case | `modules/chat/` |
| Python 文件 | snake_case | `factory.py`, `rag_engine.py` |
| API 路径 | kebab-case | `/api/v1/chat/sessions/{session_id}` |
| Pydantic 类 | PascalCase + 后缀 | `ChatRequest`, `SessionResponse` |
| ORM 模型 | PascalCase + 单数 | `class User(Base):` |
| 函数/方法 | snake_case | `astream_chat()`, `get_llm()` |
| 枚举 | PascalCase | `VoyageModel`, `BusinessCode` |
| 常量 | UPPER_SNAKE_CASE | `API_V1_STR`, `SQLITE_PATH` |

---

## 实现状态总览

| 组件 | 状态 | 说明 |
|---|---|---|
| FastAPI 应用框架 | ✅ 完成 | Lifespan、路由挂载、统一响应 |
| 统一响应框架 | ✅ 完成 | UnifiedRoute + BusinessCode + 异常体系 |
| Chat SSE 流式对话 | ✅ 完成 | LangGraph Agent + SQLite checkpointer |
| 多模型 LLM 工厂 | ✅ 完成 | 5 模型、自动 Provider 推断 |
| 对话状态持久化 | ✅ 完成 | LangGraph AsyncSqliteSaver |
| 会话 ID 管理 | ✅ 完成 | sess_{uuid} 格式生成 |
| Auth 鉴权 | Stub | 硬编码 fake-token |
| Itineraries 行程规划 | Stub | 占位 service |
| Knowledge RAG 知识库 | Stub | 占位 service，依赖已声明 |
| Redis 短期记忆 | 未开始 | 方案已设计，memory.py 为空 |
| Multi-Agent 路由 | 未开始 | 单 Agent，无子 Agent |
| 数据库 ORM | 未开始 | shared/db/ 为空，无模型 |
| RAG Pipeline | 未开始 | rag_engine.py 为空，依赖已就绪 |
| Agent 工具 (MCP/爬虫) | 未开始 | core/tools/ 为空 |
| 测试覆盖 | 极少 | 1 个测试文件，无 fixtures |

---

## 开发环境

```bash
# 安装依赖
uv sync

# 启动服务
uvicorn app.main:app --reload

# 运行测试
pytest

# 代码检查
ruff check .
black --check .
```

---

## 相关文档

- `data/docs/Voyage-AI-Travel-Planner-PRD.md` — 产品需求文档
- `data/docs/redis短期记忆方案.md` — Redis 短期记忆三阶段方案
