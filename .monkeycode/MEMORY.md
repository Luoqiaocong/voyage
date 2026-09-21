# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries

[Project Knowledge Summary]
- Date: 2026-09-19
- Context: Discovered by Agent while deploying the project via Docker Compose in /workspace
- Category: Operations & Deployment
- Instructions:
  - 部署入口：在 /workspace 执行 `DOCKER_BUILDKIT=1 docker compose up -d --build`，会构建并启动 web / backend / postgres / redis 四个容器。
  - 仅宿主 80 端口对外暴露（web 容器，可用 WEB_PORT 覆盖）；backend、postgres、redis 仅在 compose 内网可达。
  - 预览方式：使用 request_preview 暴露宿主 80 端口，生成地址形如 `https://80-<hash>.monkeycode-ai.online`。
  - 前端 API 前缀为 `/api/v1`，由 nginx 将 `/api/` 反代到 backend:8000；`/openapi.json`、`/health` 等非 /api 路径会被 SPA 回退到 index.html，不能用作后端健康检查。
  - 容器全部健康后，`curl http://127.0.0.1/api/v1/users/` 返回 405、`/api/v1/itineraries/` 返回 401 表示前后端链路正常。
  - 后端镜像构建耗时较长（约 8-12 分钟），主要开销在 `.venv` 拷贝与 `chown -R /app`；后端 CMD 先执行 `alembic upgrade head` 再启动 uvicorn。
  - 若 backend 容器反复 Restarting 且日志报 `alembic: not found`，说明构建所用 `uv.lock` 未包含 alembic，需要更新锁文件后重新构建镜像。
  - `docker compose` 子命令在本环境不可用（会被 docker 当作未知命令），统一使用 `docker-compose`。
  - 邮件收不到验证码且接口仍返回 200：多为发件地址问题，`MAIL_FROM_ADDRESS` 必须是 Resend 已验证域名下的地址；`app/shared/utils/mailer.py` 会静默吞掉 SMTP 异常，需在容器内直连 smtp.resend.com 复现才能看到真实报错。

[Project Knowledge Summary]
- Date: 2026-09-19
- Context: Discovered by Agent while diagnosing "对话没有信息返回"
- Category: Troubleshooting & Debugging
- Instructions:
  - 对话无返回的根因可能是运行环境无法访问模型网关 `opencode.ai`：`app/core/ai/llm.py` 无条件走 `OPENCODE_GO_URL`，域名不通时 LLM 调用会挂起（httpx 60s 超时 + LangChain 重试），SSE 已返回 200 但正文为空，最终由 `conversation/service.py` 抛出「AI 服务暂时不可用」。
  - 快速判定方法：`docker exec voyage-backend sh -c 'curl -sS -o /dev/null -w "%{http_code} %{time_total}\n" --max-time 12 https://opencode.ai/zen/go/v1/models'`；超时即环境出口被限制（对照组：api.resend.com / www.google.com / github.com 可达）。
  - 同类问题：启动日志 `[mcp] namespace 'travel' 不可用`、travel 工具数为 0，也是容器外网受限导致 DuckDuckGo MCP 拉取失败。
  - 出口策略需平台侧放行，容器内无法修改（且禁止在环境内改动防火墙/搭建代理）。

[Project Knowledge Summary]
- Date: 2026-09-19
- Context: Discovered by Agent while adding DeepSeek channel support so chat works under restricted egress
- Category: Environment Configuration
- Instructions:
  - LLM 通道由 `.env` 的 `LLM_CHANNEL` 决定：`opencode`（默认，走 `OPENCODE_GO_URL`）/ `deepseek`（走 `DEEPSEEK_BASE_URL`）/ `senseaudio`（走 `SENSEAUDIO_BASE_URL`）/ `zhipu`（走 `ZHIPU_BASE_URL`）；解析逻辑在 `app/core/ai/llm.py` 的 `_resolve_channel()`。
  - 关闭思考的参数因网关而异：智谱用 `extra_body={"thinking":{"type":"disabled"}}`（同时不能带 reasoning_effort），其余通道用 `reasoning_effort="none"`；映射逻辑在 `get_llm()`。
  - 智谱通道（`open.bigmodel.cn/api/paas/v4`，本环境可达）：当前用 `glm-4.5-air`（0.8/2 元每百万 token，可关思考，多工具调用稳定）。**glm-5.x 系（含 glm-5.3-flash）是「始终思考」，拒绝关闭思考并直接 400，不可用作该通道模型**。`reasoning_effort=none` 对 glm-4.x 无效（仍会思考），必须用 thinking disabled。
  - 当环境无法访问 `opencode.ai` 时，切到 DeepSeek 通道：`LLM_CHANNEL = deepseek`，`DEEPSEEK_API_KEY`（用户提供，写入 .env，勿提交），`DEEPSEEK_LLM_MODEL_FLASH = deepseek-flash`。`api.deepseek.com` 在本环境可达。
  - SenseAudio 通道（`api.senseaudio.cn`，本环境可达）：`LLM_CHANNEL = senseaudio`、`SENSEAUDIO_API_KEY`（用户提供，勿提交）、`SENSEAUDIO_LLM_MODEL = glm-5.3-flash`（模型 id 带连字符，`GET /v1/models` 可查：`glm-5.2`、`glm-5.3-flash`）。支持 `tool_choice` auto/required/指定函数，结构化提取可正常工作。
  - glm-5.3-flash 报价（人民币/百万 token）：输入 0.8、输出 2.8。配置在 `MODEL_PRICING_CNY`，看板统一美元展示，按 `CNY_PER_USD`（默认 7.2）折算；汇率波动时改这一项。
  - DeepSeek 通道的模型：`deepseek-flash`、`deepseek-v4-pro`（`GET /v1/models` 可查）；结构化提取必须用 `with_structured_output(method="function_calling")`，默认的 json_schema 方式会 400。
  - 通道相关请求头注入在 `app/core/ai/opencode.py`：仅当 `LLM_CHANNEL=opencode` 时才发 `x-opencode-session`。
  - 验证命令：容器内 `curl -sS -o /dev/null -w "%{http_code}" https://api.deepseek.com/v1/models -H "Authorization: Bearer <key>"` 应 200。
  - Dockerfile 已改为 `COPY --chown=voyage:voyage` 拷贝业务代码、chown 仅作用于 `/app/data`，backend 重建从约 6 分钟降至约 1 分钟。

[Project Knowledge Summary]
- Date: 2026-09-20
- Context: Discovered by Agent while redeploying after pulling upstream logging changes
- Category: Troubleshooting & Debugging
- Instructions:
  - backend 的 `/app/data` 是宿主 bind mount（`/workspace/data`），会覆盖镜像内已 chown 的目录；容器以 `voyage(uid 10001)` 运行，宿主目录若属 root 则无法写日志。
  - 症状：启动日志报 `[log] 文件日志不可用，已降级为仅控制台输出：PermissionError: '/app/data/output'`。
  - 修复：在宿主执行 `mkdir -p data/output/logs data/exports && chown -R 10001:10001 data`，再 `docker-compose restart backend`。`data/` 已在 .gitignore，不影响仓库。
  - 全新部署或重建数据目录后需重复此授权。
