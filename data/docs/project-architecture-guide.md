# Voyage 项目架构指南

## 目录全景

```
voyage/
│
├── app/                          # ──── 应用主代码 ────
│   ├── main.py                   # FastAPI 应用工厂 (create_app)
│   ├── config.py                 # Pydantic Settings (DB/Redis/LLM/Agent)
│   │
│   ├── api/                      # API 路由层 — 只做路由+校验，不写业务
│   │   ├── deps/                 # 依赖注入 (get_db, get_current_user, rate_limiter)
│   │   └── v1/                   # API v1 分组
│   │       ├── auth.py           # POST /auth/register, /auth/login, /auth/refresh
│   │       ├── users.py          # GET/PATCH /users/me
│   │       ├── chat.py           # POST /chat/sessions/:id/messages (SSE 流式)
│   │       ├── itineraries.py    # CRUD /itineraries + /:id/nodes + reorder
│   │       ├── budgets.py        # CRUD /itineraries/:id/budget-items
│   │       ├── checklists.py     # CRUD /itineraries/:id/checklist
│   │       ├── footprints.py     # GET /footprints, /footprints/stats
│   │       ├── rag.py            # POST /admin/documents/upload (Admin)
│   │       ├── templates.py      # CRUD /admin/templates (Admin)
│   │       └── admin.py          # GET /admin/stats/*
│   │
│   ├── core/                     # 核心业务 — 纯逻辑，零框架耦合
│   │   ├── agents/               # Multi-Agent 定义
│   │   │   ├── supervisor.py     # Supervisor Agent (意图路由+编排)
│   │   │   ├── travel.py         # 出行 Agent (MCP 查车票)
│   │   │   ├── weather.py        # 天气 Agent (爬虫)
│   │   │   ├── poi.py            # POI Agent (景点/美食/酒店)
│   │   │   └── budget.py         # 算账 Agent
│   │   ├── tools/                # Agent 工具
│   │   │   ├── mcp_client.py     # MCP 协议客户端
│   │   │   └── web_crawler.py    # 通用爬虫
│   │   ├── rag/                  # RAG 引擎
│   │   │   ├── ingestion.py      # 文档入库流水线 (切块→嵌入→写入)
│   │   │   ├── retriever.py      # 检索器 (hybrid search + reranker)
│   │   │   └── chunker.py        # 切块策略 (SentenceSplitter)
│   │   └── services/             # 业务服务层 — 编排 db + agent + rag
│   │       ├── itinerary_service.py   # 行程 CRUD 业务
│   │       ├── chat_service.py        # 对话管理 + Agent 编排
│   │       ├── budget_service.py      # 预算计算逻辑
│   │       └── footprint_service.py   # 足迹聚合逻辑
│   │
│   ├── db/                       # 数据访问
│   │   ├── session.py            # SQLAlchemy async session 工厂
│   │   ├── models/               # ORM 模型 (每个实体一个文件)
│   │   │   ├── user.py
│   │   │   ├── conversation.py
│   │   │   ├── message.py
│   │   │   ├── itinerary.py
│   │   │   ├── itinerary_node.py
│   │   │   ├── budget_item.py
│   │   │   ├── checklist_item.py
│   │   │   ├── document.py
│   │   │   ├── template.py
│   │   │   └── footprint.py
│   │   └── migrations/           # Alembic 迁移脚本
│   │       └── versions/
│   │
│   ├── schemas/                  # Pydantic 模型 (请求/响应)
│   │   ├── auth.py               # LoginRequest, RegisterRequest, TokenResponse
│   │   ├── user.py               # UserResponse, PreferencesUpdate
│   │   ├── chat.py               # MessageRequest, SSEEvent
│   │   ├── itinerary.py          # ItineraryCreate, ItineraryResponse, NodeReorder
│   │   ├── budget.py             # BudgetItemCreate, BudgetItemResponse
│   │   ├── checklist.py          # ChecklistItemCreate, ChecklistItemResponse
│   │   ├── footprint.py          # FootprintResponse, FootprintStats
│   │   ├── rag.py                # DocumentUploadResponse
│   │   └── common.py             # 通用: PaginationMeta, ErrorResponse, ApiResponse[T]
│   │
│   ├── config/                   # 配置常量 (非敏感)
│   │   ├── settings.py           # 应用级常量
│   │   └── prompts.py            # Agent system prompt 模板
│   │
│   └── utils/                    # 工具函数
│       ├── security.py           # JWT 签发/验证, password hashing
│       ├── serializers.py        # ORM → Pydantic 转换辅助
│       └── exporters.py          # PDF/Markdown 导出
│
├── data/                         # ──── 运行时数据 ────
│   ├── docs/                     # 攻略文档源文件 (管理员上传)
│   └── exports/                  # 导出文件临时暂存
│
├── tests/                        # ──── 测试 ────
│   ├── conftest.py               # pytest fixtures (async client, test db)
│   ├── api/                      # API 集成测试
│   ├── agents/                   # Agent 单元测试
│   ├── rag/                      # RAG 检索测试
│   └── services/                 # 服务层测试
│
├── scripts/                      # ──── 运维脚本 ────
│   ├── seed_data.py              # 测试数据填充
│   ├── reindex_all.py            # 全量重索引知识库
│   └── backup_db.py              # 数据库备份
│
├── docs/                         # ──── 项目文档 ────
│   ├── Voyage-AI-Travel-Planner-PRD.md
│   └── api-spec.md               # OpenAPI 规范或人工 API 手册
│
├── pyproject.toml                # 项目元数据 + 依赖
├── .env                          # 本地环境变量 (不入库)
├── .env.example                  # 环境变量模板
├── .python-version               # Python 3.12
├── README.md
└── .gitignore
```

---

## 文件放置原则

### `app/api/v1/` — 路由层
**放什么：** FastAPI router，只做 3 件事：参数校验、调用 service、返回 response。
**不放：** 业务逻辑、数据库查询、Agent 编排。

```python
# ✅ 正确
@router.post("/itineraries")
async def create_itinerary(
    body: ItineraryCreate,
    user: User = Depends(get_current_user),
    service: ItineraryService = Depends(get_itinerary_service),
):
    result = await service.create(user.id, body)
    return JSONResponse({"data": result}, status_code=201)

# ❌ 错误 — 业务逻辑写进了路由
@router.post("/itineraries")
async def create_itinerary(...):
    db.query(...).filter(...).all()  # 不准
    agent.run(...)                   # 不准
```

### `app/core/services/` — 业务服务层
**放什么：** 编排 db + agent + rag 的业务流程。一个 service 对应一个功能模块。
**不放：** 路由装饰器、HTTP 请求/响应对象。

### `app/core/agents/` — AI Agent
**放什么：** LangChain Agent 定义，包括 prompt template、tool binding、execution logic。
**不放：** 数据库操作、HTTP 路由。

### `app/core/tools/` — Agent 工具
**放什么：** LangChain Tool 实现（MCP 调用、爬虫、API 封装）。
**不放：** Agent 编排逻辑。

### `app/core/rag/` — RAG 引擎
**放什么：** LlamaIndex 相关：文档切块、嵌入、检索、入库。
**不放：** 与 LlamaIndex 无关的代码。

### `app/db/models/` — ORM 模型
**放什么：** SQLAlchemy `DeclarativeBase` 子类，每个实体一个文件。
**规则：** 字段名 = `snake_case`，统一使用 `uuid` 主键，时间戳字段名 `created_at` / `updated_at`。

### `app/schemas/` — Pydantic 模型
**放什么：** API 请求/响应数据结构，使用 Pydantic v2。
**规则：** 请求用 `*Request` / `*Create` / `*Update`，响应用 `*Response` / `*Public`。

### `app/config/` — 配置
**放什么：** 不敏感的应用常量、Agent prompt 模板、枚举定义。
**不放：** 敏感信息（放 `.env`）、API key（放 `.env`）。

### `tests/` — 测试
**命名规范：** `test_<模块名>.py`
**目录对应：** `tests/api/` 测 `app/api/`，`tests/agents/` 测 `app/core/agents/`，依此类推。

---

## 依赖方向

```
api/v1/*.py  →  core/services/*.py  →  core/agents/*.py + db/models/*.py + schemas/*.py
                core/services/*.py  →  core/rag/*.py
api/v1/*.py  →  schemas/*.py (请求/响应模型)
core/agents/*.py  →  core/tools/*.py
```

**禁止反向依赖：** `core/` 不得 import `api/` 的任何东西。

---

## 命名规则

| 类型 | 规则 | 示例 |
|---|---|---|
| 目录 | snake_case | `app/core/services/` |
| Python 文件 | snake_case | `itinerary_service.py` |
| API 路由 | kebab-case | `/api/v1/itineraries/:id/nodes` |
| Pydantic 类 | PascalCase + 后缀 | `ItineraryCreate`, `ItineraryResponse` |
| ORM 模型 | PascalCase + 单数 | `class ItineraryNode(Base):` |
| 函数/方法 | snake_case | `create_itinerary()`, `get_user_by_email()` |