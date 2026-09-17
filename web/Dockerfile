# ============================================================================
# Voyage 前端镜像：Node 构建 → nginx 提供服务
#
# 构建上下文是 **web/ 目录**：
#   docker build -f web/Dockerfile -t voyage-web ./web
#
# nginx 除了托管静态资源，还把 /api 反代到后端容器。
# 这样浏览器只看到一个源，既省掉 CORS 配置，也避免把后端端口暴露到公网。
# ============================================================================

# ---------- 阶段 1：构建 ----------
FROM node:22-bookworm-slim AS builder

WORKDIR /web

# 先拷清单文件：依赖不变时 npm ci 这层直接命中缓存
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# 同源部署：走相对路径，由下面的 nginx 反代到后端
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build


# ---------- 阶段 2：nginx ----------
FROM nginx:1.27-alpine AS runtime

# 用自定义配置替换默认站点（含 SPA 回退与 /api 反代）
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /web/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
