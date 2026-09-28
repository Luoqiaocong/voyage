# 会话交接 · 2026-09-28

分支 `feature/complete-demo`。已推送的 HEAD 为 `b09ad59`（前端重构 → 模型切换 → 滚动修复）。
**本轮「最大范围优化」的全部改动仍在工作区，未 git commit。**
唯一入库产物是 untracked 新文件，见下。

## 本轮目标

在既有系统上做尽可能广的前后端行为优化：安全、正确性、性能、无障碍。
优先修真实缺陷，不做无收益的「脚手架式完备」。

## 已完成（按主题）

### 后端 · 安全与正确性
- `user/dependencies.py` `_authenticate_token` 拒绝停用用户（`USER_ACCOUNT_DISABLED`）
- `auth/service.py` `issue_access_token` 复查用户存在且 `is_active`
- `user/auth.py` `PasswordManager.verify_uniform`：用户不存在也跑等价 Argon2，抹平登录时间侧信道；`user/service.py` 登录改用它
- `auth/service.py` `issue_reset_token` 改为「先验验证码再查用户」，未注册与验证码错误同码，防邮箱枚举
- `audit.py` `record` 不再吞异常（吞掉只会造成「改了却没记」），`json.dumps(default=str)`
- `conversation/repo.py` 新增 `increment_message_count`（原子自增）、`remove_owned`（`DELETE...RETURNING` 返回真正删除的 id，防越权清 checkpoint）；`service.py` 改用
- `itinerary/share_repo.py` `bump_view_count` 改 `UPDATE...RETURNING` 原子计数

### 后端 · 隐私（HIGH）
- 新增 `core/ai/memory_context.py`：ContextVar + `use_memory_context` + `inject_memory` dynamic_prompt 中间件
- `core/ai/agent.py` 移除 `AgentFactory` 上全局可变的 `_memory_context` / `apply_memory` / `_compose_prompt`
- `conversation/gateway.py` `_load_memory_context`，`stream_message` 用 `use_memory_context(...)` 包裹
- 效果：跨并发用户不再串记忆，且不必每轮重建 agent

### 后端 · 性能
- `user/auth.py` 新增 `hash_password_async` / `verify_password_async` / `verify_password_uniform_async`（`anyio.to_thread.run_sync`），把 Argon2（单次约 70ms）移出事件循环；`user/service.py`、`itinerary/share_service.py` 全部改异步调用
- `shared/db/models.py` 加复合索引：Conversation `ix_conversations_user_created`、Itinerary `ix_itineraries_user_updated`
- 新迁移 `alembic/versions/c4d9e7a1b2f3_add_list_query_indexes.py`，已 `upgrade head`

### 后端 · 配置化
- `config.py` `ZHIPU_ALWAYS_THINKING_MODELS=["glm-5","glm-5.*"]`；`core/ai/llm.py` 新增 `_matches_model_pattern`，`_zhipu_always_thinking` 改配置驱动（不再硬编码）
- `shared/utils/datetime_util.py` `LOCAL_TZ=ZoneInfo(config.APP_TIMEZONE)`；`core/ai/tasks/gen_title.py` 去硬编码时区

### 前端 · 无障碍
- `ItineraryDetailView.vue`、`SharePanel.vue`、`ProfileView.vue` 补输入控件 `aria-label`
- `ChatView` 侧栏抽屉：Esc 关闭
- `ConfirmHost.vue`：补全对话框键盘可达性 —— 打开时聚焦首个按钮、Tab 在框内循环（焦点陷阱）、Esc 取消、关闭后把焦点归还触发元素

### 前端 · 竞态与清理
- `ChatView.vue`：onUnmounted `abortCtl?.abort()`；会话切换竞态用代次 `convReq` 校验（`openConversation` / `newConversation`）
- `useChatAutoScroll.ts` `jumpTimer` 卸载清理
- `ItinerariesView.vue`、`admin/AdminUsers.vue`、`admin/AdminAudit.vue` 防抖定时器 onUnmounted 清理

### 前端 · 渲染性能
- `MessageBody.vue`：把模板里的 `toSpans` / `groupBySlot` / `detectSlot` / `stripSlotPrefix`
  全部前置进 `view` computed（表格几十个单元格、行程多天时每次重渲染都要重跑），模板不再调用函数
- `ItineraryDetailView.vue`：`groupBySlot + sortGroupsBySlot` 从模板搬进 `groupedDays` computed

### 测试
- 新增 `tests/test_hardening.py`（16 通过）：密码时间侧信道、模型匹配、记忆隔离、时区口径、单例无可变记忆
- `tests/test_frontend_a11y.py` 扫描器加强（识别自闭合输入控件），6 通过 / 0 失败

## 验证（本轮已通过）

- `cd web && npx vue-tsc --noEmit` → 通过
- `cd web && npx vite build` → 通过
- `python3 tests/test_frontend_a11y.py` → 6 / 0
- 后端批量（容器内，`--network container:voyage-backend`）：
  `test_admin_roles` `test_admin_roles_e2e` `test_audit_privacy` `test_config_cleanup`
  `test_date_context` `test_deploy_config` `test_docker_consistency` `test_itinerary_dates`
  `test_itinerary_extract_limit` `test_memory_dedup` `test_role_consistency`
  `test_session_refresh` `test_share_patch` `test_share_privacy_health`
  `test_token_attribution` `test_validation_messages` `test_admin_time_format`
  `test_tool_metrics` `test_tool_metric_shape` `test_subagent_loop_guard`
  `test_mcp_platform` `test_hardening` → 全部 PASS

基线既有失败（非本轮引入，已确认）：`test_resend`（交互式 EOFError）、
`test_supervisor_agent`（镜像无 pytest）、`test_vue_sfc`（镜像无 node）。

## 运行照抄命令

```bash
# 后端测试（共享网络命名空间，127.0.0.1:8000 命中运行中的后端）
docker run --rm --network container:voyage-backend \
  -e REDIS_URL=redis://redis:6379/7 \
  -e DATABASE_URL=postgresql+asyncpg://voyage:voyage@postgres:5432/voyage \
  -v /workspace:/src -w /src voyage-backend:latest \
  python tests/test_hardening.py
```

## 待办 / 未做

- 运行中的后端仍是旧镜像，本轮改动需重建容器才生效（前端 dist 已重建）
- 评估后降优先级（未做）：记忆提取 N+1、会话列表分页、`get_task_llm` 缓存、
  ChatView/HomeView 再拆分、`SearchModal` 焦点陷阱、前端 lint/format 工具

## 入库产物（untracked，需 add）

- `app/core/ai/memory_context.py`
- `alembic/versions/c4d9e7a1b2f3_add_list_query_indexes.py`
- `tests/test_hardening.py`

## 模型（沿用，未改）

- `.env`（gitignored）：`LLM_CHANNEL=zhipu`、`ZHIPU_LLM_MODEL=glm-5.3-flash`、思考强度固定 low
- 该模型「始终思考」，关闭会 400；`_zhipu_always_thinking` 对其跳过禁用参数

## 约束

- `docker-compose`；仅宿主 80；密钥勿提交；勿 publish-website
- 本轮改动默认**不 commit**，等明确指示
