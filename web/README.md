# Voyage Web

Voyage AI 的现代 Web 前端（Vue 3 + Vite + TypeScript + Pinia + Vue Router），浅色主题，后端全部功能已对接。

## 功能清单

- 用户：登录 / 注册（邮箱验证码）/ 两步找回密码 / 资料与头像库修改 / 修改密码 / 登出 / 注销账号
- 令牌：access + refresh 双 token，401 自动刷新重试
- 会话：列表 / 新建 / 重命名 / 删除 / 历史消息（按轮次分页，字段已收敛）
- AI 对话：POST SSE 流式（text / tool_call / tool_result / reasoning / title / error / done），工具调用时间线、思考过程折叠、Markdown 轻渲染
- 行程：对话内一键提取 / 列表 / 详情 / 局部字段编辑（PATCH）/ 删除；整体替换（PUT）接口已封装在 api/itinerary.ts
- 行程导出：日历 `.ics`（可导入手机日历）/ Markdown / 打印页（浏览器 Ctrl+P 存 PDF）
- 行程分享：创建带权限、密码与有效期的分享链接；公开分享页支持密码门槛、只读展示、按权限复制
- 长期记忆：查看助手从对话中提炼的偏好，可修正取值、停用、删除、一键清空
- 管理台：看板（Token 消耗/用户增长/成本估算/系统健康）、运行指标（缓存命中率、结构校验通过率、延迟分位）、用户管理（改角色/禁用）、会话洞察、审计日志、CSV 导出

## 快速开始

前置：Node >= 18，后端已在本机 8000 端口启动（uvicorn app.main:app --port 8000）。

    npm install
    npm run dev

打开 http://127.0.0.1:5173。

> 管理台需要管理员账号：用后端脚本创建后再登录即可看到「管理台」入口。
> `uv run python app/scripts/create_admin.py --email you@example.com --username 你的昵称`

## 环境变量

复制 .env.example 为 .env：

    VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1

## 构建

    npm run build   # vue-tsc 类型检查 + vite build
    npm run preview

## 目录说明

- src/api —— axios 封装（统一解包 {code, message, data} + 401 自动 refresh）与各业务接口；
  `http.ts` 另导出 `downloadFile` / `openTextExport`，供文件导出走原始响应
- src/stores —— user（token/资料/角色）、ui（toast/confirm 全局交互）
- src/views —— 落地页、登录/注册/找回、对话、行程、个人中心、公开分享页
- src/views/admin —— 管理台（含侧栏布局与 5 个子页面）
- src/components —— 导航、页脚、插画、Toast/Confirm 浮层、分享面板、记忆面板
- src/components/charts —— 手写 SVG 折线/条形图（不依赖图表库）

## 页面路由

| 路由 | 页面 | 鉴权 |
|---|---|---|
| / | 主页落地页 | 公开 |
| /login | 登录 / 注册 / 找回密码 | 未登录 |
| /chat | AI 对话（SSE）| 登录 |
| /itineraries | 我的行程列表 | 登录 |
| /itineraries/:id | 行程详情、导出与分享管理 | 登录 |
| /profile | 个人资料、账号安全与长期记忆 | 登录 |
| /share/:token | 公开分享页 | 公开（可选密码）|
| /admin | 管理台概览 | 管理员 |
| /admin/metrics | 运行指标 | 管理员 |
| /admin/users | 用户管理 | 管理员 |
| /admin/conversations | 会话洞察 | 管理员 |
| /admin/audit | 审计日志 | 管理员 |

> 前端的 `requiresAdmin` 守卫只是「界面不展示 + 少发无谓请求」，
> 真正的权限边界在后端：`/api/v1/admin/*` 统一挂了管理员依赖，非管理员返回业务码 10105。
