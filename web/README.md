# Voyage Web

Voyage AI 的现代 Web 前端（Vue 3 + Vite + TypeScript + Pinia + Vue Router），浅色主题，后端全部功能已对接。

## 功能清单

- 用户：登录 / 注册（邮箱验证码）/ 两步找回密码 / 资料与头像库修改 / 修改密码 / 登出 / 注销账号
- 令牌：access + refresh 双 token，401 自动刷新重试
- 会话：列表 / 新建 / 重命名 / 删除 / 历史消息
- AI 对话：POST SSE 流式（text / tool_result / reasoning / title / error / done），工具调用提示、思考过程折叠、Markdown 轻渲染
- 行程：对话内一键提取 / 列表 / 详情 / 局部字段编辑（PATCH）/ 删除；整体替换（PUT）接口已封装在 api/itinerary.ts

## 快速开始

前置：Node >= 18，后端已在本机 8000 端口启动（uvicorn app.main:app --port 8000）。

    npm install
    npm run dev

打开 http://127.0.0.1:5173。

## 环境变量

复制 .env.example 为 .env：

    VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1

## 构建

    npm run build   # vue-tsc 类型检查 + vite build
    npm run preview

## 目录说明

- src/api —— axios 封装（统一解包 {code, message, data} + 401 自动 refresh）与企业接口
- src/stores —— user（token/资料）、ui（toast/confirm 全局交互）
- src/views —— HomeView（落地页）、LoginView（登录/注册/找回）、ChatView（对话）、ItinerariesView / ItineraryDetailView（行程）、ProfileView（个人中心）
- src/components —— 导航、页脚、Hero 插画、Toast / Confirm 浮层

## 页面路由

| 路由 | 页面 | 鉴权 |
|---|---|---|
| / | 主页落地页 | 公开 |
| /login | 登录 / 注册 / 找回密码 | 未登录 |
| /chat | AI 对话（SSE）| 登录 |
| /itineraries | 我的行程列表 | 登录 |
| /itineraries/:id | 行程详情与编辑 | 登录 |
| /profile | 个人资料与账号安全 | 登录 |
