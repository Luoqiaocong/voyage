# Voyage 部署 RUNBOOK

面向「部署到自己的服务器」的完整步骤。命令可直接复制执行。

- 形态：**单域名 + nginx 反代 + HTTPS**
- 拓扑：`公网 80/443 → Caddy（自动证书）→ web 容器 → /api/ → backend → PostgreSQL / Redis`
- 前提：一台能装 Docker 的 Linux 服务器、一个已解析到该服务器的域名

> **关于跨域**：本方案下前端与 `/api` 同源（都由同一个域名提供），
> 浏览器不会发起跨域请求，**CORS 不参与**。仍建议把 `ALLOWED_ORIGINS`
> 设为该域名做纵深防御，见第 3 步。

---

## 0. 前置检查

```bash
# 系统与架构
uname -a && cat /etc/os-release | head -3

# Docker 是否已装（没装见第 1 步）
docker --version && docker compose version

# 磁盘空间：镜像 + 数据库 + 日志，建议留 10 GB 以上
df -h /

# 80 / 443 是否被占用（被占用则 Caddy 起不来）
sudo ss -lntp | grep -E ':(80|443)\b' || echo "80/443 空闲"
```

**预期**：`docker --version` 输出版本号；`ss` 那条输出「空闲」。
若 80/443 被 nginx/apache 占用，需先停掉它们（`sudo systemctl stop nginx`），
否则第 5 步 Caddy 会因端口冲突启动失败。

---

## 1. 安装 Docker（已装则跳过）

```bash
# 官方脚本，装 Docker Engine + compose plugin
curl -fsSL https://get.docker.com | sudo sh

# 让当前用户免 sudo 使用 docker（需重新登录生效）
sudo usermod -aG docker $USER

# 重新登录后验证
docker run --rm hello-world
docker compose version
```

> ⚠️ `usermod` 之后**必须重新登录**（退出 SSH 再连），否则 `docker` 仍要 sudo。
> 不想重登就执行 `newgrp docker` 开一个子 shell。

---

## 2. 取代码

```bash
# 换成你自己的仓库地址
git clone https://github.com/Luoqiaocong/voyage.git
cd voyage

# 确认在正确的分支上
git branch --show-current     # 预期：feature/complete-demo
git log --oneline -1
```

---

## 3. 配置 .env（**这一步最关键**）

```bash
cp .env.example .env
```

### 3.1 生成两份必须重新生成的密钥

```bash
# JWT 签名密钥与密码哈希盐。**绝不要复用本地 .env 里的值**——
# 那对密钥已在本机文件里存在很久，且本地库的数据已清空，
# 没有沿用它们的理由。
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
echo "HASH_SALT=$(openssl rand -hex 16)"
```

把输出逐行填进 `.env`。

### 3.2 填写域名与部署项

在 `.env` 中加入/修改以下内容（`<...>` 换成你的实际值）：

```ini
# ---- 对外域名（Caddy 用它申请证书，必须已解析到本机）----
DOMAIN=<你的域名，如 voyage.example.com>
ACME_EMAIL=<你的邮箱，证书到期通知用>

# ---- 分享链接的对外基址 ----
# 不设置的话，分享出去的链接会是 http://localhost/share/... 别人打不开
SHARE_BASE_URL=https://<你的域名>

# ---- 容器内 PostgreSQL 的密码（compose 默认值是 voyage，必须改）----
POSTGRES_PASSWORD=<用 openssl rand -hex 16 生成>

# ---- CORS 白名单（纵深防御）----
# 同源部署下浏览器不发跨域请求，这项不参与实际放行；
# 但后端在 ALLOWED_ORIGINS 留空时会回显任意 Origin 并允许携带凭据，
# 填上即收窄为白名单。
ALLOWED_ORIGINS=["https://<你的域名>"]

# ---- 模型与邮件密钥（沿用你现有的值）----
# 默认走 OpenCode Go 通道，配这三项即可
OPENCODE_GO_URL=...
OPENCODE_API_KEY=...
RESEND_API_KEY=...
```

> **LLM 通道可切换**：由 `LLM_CHANNEL` 决定，可选
> `opencode`（默认）/ `deepseek` / `senseaudio` / `zhipu`。
> 切到别的通道时，填对应的 `*_API_KEY` 与 `*_BASE_URL`（见 `.env.example`），
> 未选中的通道其密钥留空不影响启动。解析逻辑在 `app/core/ai/llm.py`。
>
> 关闭思考的参数因网关而异：智谱用 `extra_body={"thinking":{"type":"disabled"}}`，
> 其余通道用 `reasoning_effort="none"`。
>
> **glm-5.3-flash 的思考能力因网关而异（均已实测）**：
> - 智谱直连：`glm-5.3-flash` 为「始终思考」，只接受 `reasoning_effort` 的
>   `low/high/max`，传 `thinking={"type":"disabled"}` 或 `reasoning_effort="none"`
>   直接 400。框架会按模型名自动改用 `ZHIPU_ALWAYS_THINKING_EFFORT`（默认 `low`），
>   其强制 `tool_choice` 原生可用。**务必保留 low 档**：实测不传档位时走默认档，
>   正文首字可到 40s+、reasoning token 很高；`low` 档 reasoning token 归零、
>   正文首字约 0.7s。
> - SenseAudio 网关：同名模型接受 `reasoning_effort="none"` 并真正关闭思考，
>   强制 `tool_choice` 也返回原生 `tool_calls`。**要在 glm-5.3-flash 上不思考，
>   请用 `LLM_CHANNEL=senseaudio`**。
> - 智谱直连若必须关思考：改用 `glm-4.5-air`（实测可关，无 `reasoning_content`），
>   但它的强制 `tool_choice` 不返回原生 `tool_calls`，提取会退到提示词回退路径。

> **`DATABASE_URL` / `REDIS_URL` 不用填**：compose 已覆盖为容器内的
> postgres 与 redis 服务地址（见 docker-compose.yml 的 environment 段）。
> 留空或用 .env.example 里的占位值都不影响容器部署。

> **邮件发件地址**：`MAIL_FROM_ADDRESS` 必须是 Resend 已验证域名下的地址。
> 用了未验证的地址时，接口仍返回成功（`mailer.py` 会吞掉 SMTP 异常），
> 但邮件永远收不到 —— 表现为「验证码发不出去又看不到报错」。

### 3.3 收紧文件权限

```bash
chmod 600 .env
```

---

## 4. 先跑 HTTP 验证（**别急着上 HTTPS**）

先用 IP + HTTP 确认应用本身能起来。这样出问题时能确定是应用问题还是证书问题，
排查面小一半。

```bash
# 临时用 80 端口
docker compose up -d --build

# 看启动过程（首次会构建镜像，几分钟）
docker compose logs -f backend
```

**预期日志**（关键几行）：
```
[checkpoint] 使用 PostgreSQL 作为会话状态后端（连接池）
[mcp] namespace 'travel' 工具就绪：8 个
[prewarm] travel 工具已就绪（8 个），耗时 ...
Application startup complete.
Uvicorn running on http://0.0.0.0:8000
```

```bash
# 四个容器都应是 Up (healthy)
docker compose ps

# 健康检查
curl -I http://localhost/            # 预期 HTTP/1.1 200
curl -s http://localhost/api/v1/users/avatars | head -c 200
```

浏览器打开 `http://<服务器IP>/`，注册第一个账号——**它会自动成为管理员**。
能注册成功说明：前端、nginx 反代、后端、PostgreSQL、Redis 全链路通了。

> 若这里就不通，**先不要继续**。见文末「故障排查」。

---

## 5. 启用 HTTPS

```bash
# 用叠加文件把 Caddy 加进来，并启动
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml up -d

# 看证书申请过程
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml logs -f caddy
```

**预期日志**：
```
certificate obtained successfully  identifier=<你的域名>
```
首次申请通常 10~30 秒。

```bash
# 验证证书与跳转
curl -I https://<你的域名>                      # 预期 200
curl -I http://<你的域名>                       # 预期 308 跳转到 https
echo | openssl s_client -connect <你的域名>:443 -servername <你的域名> 2>/dev/null \
  | openssl x509 -noout -subject -dates
```

浏览器打开 `https://<你的域名>/`，确认锁标正常、登录与对话功能可用。

### 把 HTTP 版本关掉

第 4 步用的是「web 直接暴露 80」，第 5 步叠加文件已用 `ports: !reset []`
把它收回。确认无误后可检查一下：

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml ps
# web 不应再有 0.0.0.0:80->80 的端口映射，80/443 应归属 voyage-caddy
```

---

## 6. 数据初始化状态确认

```bash
# 库应为空（若你在本地已清空过，这里也是干净的）
docker compose exec postgres psql -U voyage -d voyage -c \
  "select count(*) as users from users;"
```

部署后的**第一个注册用户即管理员**。这一点在设计上是「一次性引导」：
一旦有人注册，该通路永久关闭。

> ⚠️ 因此请在**关闭公网访问或先完成注册**之后再对外公布地址，
> 否则理论上存在被他人抢先注册为管理员的风险。

---

## 日常运维

### 更新基础镜像

本项目为可复现性固定了镜像版本（**刻意不用 `latest`**），但固定之后就没人会
注意到上游发了带安全修复的新版——本项目就踩过：前端一直停在 nginx 1.27，
而该分支早已停止维护，后续安全修复都拿不到。

更新的正确做法是让 Docker 自己判断：

```bash
# 构建时强制拉取基础镜像的最新版本（本项目用的是 1.30-alpine 这类
# 滚动标签，会自动解析到该系列的最新 patch）
docker compose build --pull

# 重新创建容器并清掉旧镜像
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml up -d
docker image prune -f

# 查看哪些镜像有更新
docker compose pull
```

> **关于「要不要写死 patch 号」**：不要。
> `nginx:1.30-alpine` 这类滚动标签**始终指向该系列的最新 patch**，
> 写成 `1.30.5-alpine` 反而会错过后续的 1.30.6、1.30.7。
> 只有**跨系列**（如 1.30 → 1.31）才需要人工决定，因为可能引入不兼容变更。
>
> 判断某个系列是否已停止维护，看官方发布说明，不要看版本号大小——
> nginx 的 1.31 是 mainline、1.30 是 stable，**号大不代表更适合生产**。

### 其他常用命令

```bash
# 更新代码后重新部署
git pull
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml up -d --build

# 日志
docker compose logs -f backend          # 后端
docker compose logs -f caddy            # 证书与访问日志
docker compose logs --tail=100 web      # nginx

# 数据库备份（导出到宿主机当前目录）
docker compose exec -T postgres pg_dump -U voyage -d voyage | gzip > backup-$(date +%F).sql.gz

# 资源占用
docker stats --no-stream

# 停止（保留数据卷）
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml down
```

> ⚠️ **不要执行 `docker compose down -v`**：`-v` 会删除数据卷，
> 包括 `pg-data`（业务数据）与 `caddy-data`（证书）。删证书还会因
> Let's Encrypt 的签发次数限制而暂时无法重新申请。

> ⚠️ **PostgreSQL 跨大版本不能直接换镜像**。当前用的是 18，若是已有数据的
> 实例要升到 19 之类，必须走 `pg_upgrade` 或逻辑导出导入；直接改
> `image:` 会因数据目录版本不匹配而启动失败。

---

## 故障排查

### 80/443 被占用，Caddy 起不来
```bash
sudo ss -lntp | grep -E ':(80|443)\b'
sudo systemctl stop nginx apache2 httpd 2>/dev/null
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml up -d
```

### 证书申请失败
排查顺序（从最常见开始）：
```bash
# 1. 域名是否解析到本机 IP
dig +short <你的域名>
curl -s ifconfig.me; echo

# 2. 80 端口能否从公网访问（Let's Encrypt 的 HTTP-01 校验要用）
curl -I http://<你的域名>/.well-known/acme-challenge/test
# 若用了云厂商安全组/防火墙，需放行 80 与 443

# 3. Caddy 的具体报错
docker compose logs caddy | tail -40
```
常见原因：DNS 未生效、云安全组未放行 80、域名解析到了 CDN 而非本机。

### 页面能打开但接口 502
说明 Caddy/nginx 通了但 backend 没起来：
```bash
docker compose ps                      # backend 是否 healthy
docker compose logs --tail=80 backend  # 看报错
```
常见原因：`DATABASE_URL` 被 `.env` 覆盖成了外部地址、模型 API Key 无效导致启动失败。

### AI 回复不是逐字输出，而是一整段蹦出来
两层代理都可能缓冲，本项目已在两处都关掉了：
- `web/nginx.conf`：`proxy_buffering off`
- `deploy/Caddyfile`：`flush_interval -1`

若仍有此现象，检查是否在 Caddy 之前还挂了别的反代（如 Cloudflare），
需要在那一层也关闭缓冲。

### 登录/注册报 500
```bash
docker compose logs --tail=50 backend | grep -iE "error|exception"
```
Redis 相关报错居多。确认 redis 容器 healthy：`docker compose ps`。

### 启动日志报文件日志不可用（PermissionError: '/app/data/output'）
`/app/data` 是宿主 bind mount，会覆盖镜像内已授权好的目录；容器以
`voyage(uid 10001)` 运行，宿主目录若属 root 就写不进去（日志降级为仅控制台）。
在宿主机执行后重启即可，重建数据目录后需重复一次：
```bash
mkdir -p data/output/logs data/exports && chown -R 10001:10001 data
docker compose restart backend
```

### backend 反复 Restarting，日志报 `alembic: not found`
说明构建镜像用的 `uv.lock` 里没有 alembic（后端 CMD 会先跑 `alembic upgrade head`）。
确认 `alembic` 已在 `pyproject.toml` 的 dependencies 中并更新锁文件后重新构建。

### 对话没有内容返回 / 日志报 MCP 命名空间不可用
先确认容器能否访问模型网关与 MCP 依赖源：
```bash
docker exec voyage-backend sh -c \
  'curl -sS -o /dev/null -w "%{http_code} %{time_total}\n" --max-time 12 \
   https://opencode.ai/zen/go/v1/models'
```
超时说明出口被限制（此时 LLM 调用会挂起：SSE 已返回 200 但正文为空，
最终由 `conversation/service.py` 报「AI 服务暂时不可用」）。
同类现象是日志出现 `[mcp] namespace 'travel' 不可用`、工具数为 0 ——
DuckDuckGo MCP 需要在容器内联网下载。二者都需平台侧放行出口，
容器内改不了；临时办法是切到可达的 LLM 通道（见 3.2）。

---

## 与本地开发的差异

| 项 | 本地 | 服务器 |
|---|---|---|
| 启动命令 | `uv run python run.py` + `npm run dev` | `docker compose ... up -d --build` |
| 数据库 | `.env` 里指向外部 PG | compose 内 postgres 容器 |
| Redis | 本地 127.0.0.1:6379 | compose 内 redis 容器 |
| 端口 | 5173 / 8000 | 仅 80 / 443 对外 |
| TLS | 无 | Caddy 自动申请 |
| CORS | 不参与（Vite 代理） | 不参与（nginx 反代同源） |
