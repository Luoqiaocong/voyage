# 会话交接 · 2026-09-26

HEAD 仍是 `766c498` / `feature/complete-demo`。本轮重构已落盘，**尚未 git commit**。

## 本轮已完成：巨型组件拆分 + 死代码清理

目标：ChatView.vue 3632 行、HomeView.vue 2424 行，职责过多、难测试。

ChatView.vue **3632 → 2351 行**，按「会话流 / 提取 / 搜索弹窗 / 输入区」拆出：

- `components/MessageStream.vue`（会话流：消息、思考过程、工具时间线、等待态）
- `chat/composables/useItineraryExtract.ts`（提取：条件判断 + 二次确认 + 调用 + 结果引导）
- `components/SearchModal.vue`（搜索弹窗：标题/内容检索、命中片段）
- `components/ChatComposer.vue`（输入区：快捷芯片、自适应高度、按键处理）

HomeView.vue **2424 → 2160 行**：

- `composables/useVoiceInput.ts`（Web Speech 语音输入，含卸载时停止识别）
- `composables/useHomeReveal.ts`（首屏展开闸门 + 入场所见即现揭示 + 滚动/触摸意图）

死代码清理：

- 删除 `api/conversation.ts` 中零引用的 `getMessages`（原类型标注还写错）
- 删除只写不读的 `showReasoning`，以及 ChatView 内已失效的 `.chat-empty__quick` 样式
- 新增 `types/message.ts` 承载 `RdMsg`，供 ChatView 与提取 composable 共用

## 验证（已通过）

- `cd web && npx vue-tsc --noEmit` 通过
- `cd web && npx vite build` 通过
- `python3 tests/test_vue_sfc.py` 2 通过 / 0 失败
- `python3 tests/test_frontend_a11y.py`：5 通过 / 1 失败，失败项为既有问题
  （`ItineraryDetailView.vue:664` 的 textarea 缺少可访问名称，与本轮改动无关）

## 运行

- 四容器 healthy
- 预览 `https://80-44a00f9a57bbbed4.monkeycode-ai.online`
- SPA `/` `/itineraries` `/share/demo` 200

## 手测清单（登录后）

- 首页输入 → 规划页开新会话并自动发送
- 输入区：快捷芯片、Enter 发送、Shift+Enter 换行、生成中 Esc/按钮停止
- 消息区：复制、重新生成、思考过程折叠、工具时间线
- 提取：确认框、防连点、覆盖/另存、完成后不自动跳
- 搜索弹窗：标题与对话内容命中、片段预览
- 首页：滚动/上滑展开、收起回顶、语音输入（如浏览器支持）

## 模型切换：全量改用 glm-5.3-flash（2026-09-26）

- `.env`（gitignored）：`LLM_CHANNEL=zhipu`、`ZHIPU_LLM_MODEL=glm-5.3-flash`、
  `LLM_DISABLE_REASONING=false`，并更新了 `ZHIPU_API_KEY`
- 智谱直连的 `glm-5.3-flash` 为「始终思考」：关闭思考会 400，只接受
  `reasoning_effort` 的 low/high/max。故本模型**接受思考**（会有 `reasoning_content`）
- `app/core/ai/llm.py` 新增 `_zhipu_always_thinking`：对始终思考模型自动跳过
  禁用参数（含 EXTRACT 强制 tool_choice 场景），避免整体 400；警告按模型去重
- 实测：CHAT 正常；EXTRACT 的强制 `tool_choice` 返回原生 tool_calls，走主路径
- 备选：`glm-4.5-air`（智谱直连）可真正关思考，但其强制 tool_choice 不返回原生
  tool_calls，提取会退到提示词回退路径；`senseaudio` 网关的 glm-5.3-flash 可关思考
  且原生 tool_calls 可用
- 相关文档已同步：`app/config.py` 注释、`.env.example`、`deploy/RUNBOOK.md`

## 约束

- `docker-compose`；仅宿主 80；密钥勿提交；勿 publish-website
