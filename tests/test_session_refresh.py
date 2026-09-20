"""会话续期回归验证。

## 为什么必须有这个测试

本次修的是一个**每个用户都会遇到、且不影响编译**的 bug：

  后端把鉴权失败表达成 HTTP 200 + 业务码 10102（见 app/core/business/util.py），
  而前端原先只在 HTTP 401 时才用 refresh token 续期 —— 该分支永不命中。
  于是 access token 每 30 分钟过期一次，用户就被弹一次「登录已过期」，
  7 天有效的 refresh token 从未被使用。

这类 bug 的特点是：**类型检查通过、构建通过、页面也能打开**，
只是功能默默失效。只有断言「代码里确实接通了那条路」才能防它回来。

断言分两层：
  后端 —— 确认业务码定义与「业务异常返 200」的契约没变（前端修复的前提）
  前端 —— 确认业务码常量、拦截器分支、store 过期判断、跳转逻辑都在
"""
import re
import sys
from pathlib import Path

WEB = Path("web/src")
ok = bad = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global ok, bad
    ok += cond
    bad += not cond
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def strip_comments(src: str) -> str:
    """剥注释后再断言。

    本仓库的注释大量**引用被删掉的旧代码**来说明为什么改
    （例如「原先写的是 status_code=401」），直接全文匹配会把
    「已修改」误判成「仍是旧实现」。

    ⚠️ 行注释只剥**行首**的（`^\\s*//`）。不能写成 `//[^\n]*`：
    那会把字符串字面量里的双斜杠也当注释起点 ——
    `redirect.startsWith("//")` 会被从 `"//` 处截断，后面的代码全部消失，
    于是断言「挡掉了协议相对 URL」永远失败。
    （实测踩过：报 FAIL 但代码其实是对的。）
    """
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"<!--[\s\S]*?-->", "", src)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    return src


# ══════════════ 后端契约 ══════════════
print("=== 后端契约（前端修复的前提）===")
code_py = read(Path("app/core/business/code.py"))
util_py = read(Path("app/core/business/util.py"))

for name, num in (("UNAUTHORIZED", "10101"), ("TOKEN_EXPIRED", "10102"), ("TOKEN_INVALID", "10103")):
    m = re.search(rf"{name}\s*=\s*\((\d+)", code_py)
    check(f"业务码 {name} = {num}", bool(m) and m.group(1) == num,
          f"实际 {m.group(1) if m else '未找到'}")

# 业务异常必须仍返 HTTP 200 —— 若是改成 401，前端也应能工作，
# 但本测试的假设会变，故显式断言以便及时发现契约变更。
util_code = strip_comments(util_py)
m = re.search(
    r"unified_business_exception_handler[\s\S]{0,300}?status_code\s*=\s*([^,\n]+)", util_code
)
check("业务异常仍返回 HTTP 200（Token 失效走业务码而非 401）",
      bool(m) and "HTTP_200_OK" in m.group(1),
      m.group(1).strip() if m else "未匹配")

# 令牌校验处必须抛业务异常（而非 HTTPException）
dep = strip_comments(read(Path("app/modules/user/dependencies.py")))
check("依赖层令牌失效抛 UserException", "UserException(code=BusinessCode.TOKEN_INVALID)" in dep)

# ══════════════ 前端修复 ══════════════
print("\n=== 前端：拦截器识别业务码 ===")
http = read(WEB / "api/http.ts")
http_code = strip_comments(http)

check("定义了鉴权失败业务码集合",
      re.search(r"AUTH_FAILED_CODES\s*=\s*new Set\(\[[^\]]*10102", http_code) is not None)
check("集合含 10101 / 10102 / 10103",
      all(c in re.search(r"AUTH_FAILED_CODES\s*=\s*new Set\(\[([^\]]*)\]", http_code).group(1)
          for c in ("10101", "10102", "10103")))
check("成功分支里也检查业务码（不只看 HTTP 状态）",
      re.search(r"SUCCESS_CODES\.has[\s\S]{0,700}?AUTH_FAILED_CODES\.has", http_code) is not None)
check("有刷新后重放的统一入口 retryAfterRefresh",
      "async function retryAfterRefresh" in http_code)
check("刷新失败才清理会话并通知跳转",
      "handleSessionExpired" in http_code and "emitSessionExpired" in http_code)
check("用 _retry 标记防死循环重试", "_retry" in http_code)
# 关键回归点：刷新失败必须跳转，而不是只弹提示
check("刷新失败会派发会话失效事件",
      re.search(r"handleSessionExpired[\s\S]{0,200}?emitSessionExpired", http_code) is not None)
# fetchRaw（导出下载）也要覆盖
check("原生 fetch 的导出路径同样处理业务码",
      re.search(r"async function fetchRaw[\s\S]{0,1200}?AUTH_FAILED_CODES\.has", http_code) is not None)

# 旧的「只在 401 时跳转」写法必须已不存在
check("不再有仅凭 HTTP 401 就 window.location.assign 的旧逻辑",
      "window.location.assign" not in http_code)

print("\n=== 前端：store 的过期判断 ===")
store = read(WEB / "stores/user.ts")
store_code = strip_comments(store)

fn = re.search(r"async function ensureValidToken[\s\S]*?\n  \}", store_code)
body = fn.group(0) if fn else ""
check("找到 ensureValidToken", bool(body))
# 这是本次最核心的一行修复
check("ensureValidToken 检查过期（而非只判非空）",
      "isTokenExpired(accessToken.value)" in body,
      "仍是 `if (accessToken.value) return true` 的话就会回归" if "isTokenExpired" not in body else "")
check("过期后走 refresh 续期", "refreshAccessToken()" in body)
check("续期失败才 clearAuth", "clearAuth()" in body)

print("\n=== 前端：会话失效的跳转处理 ===")
main = read(WEB / "main.ts")
main_code = strip_comments(main)
check("main.ts 监听会话失效事件", "SESSION_EXPIRED_EVENT" in main_code)
check("清登录态（含 Pinia 内存态）", "clearAuth()" in main_code)
check("弹提示告知原因", "ui.toast(" in main_code)
check("跳登录页", re.search(r"name:\s*'login'", main_code) is not None)
check("带 redirect 回跳原地址", "redirect" in main_code)
check("在登录页时不重复跳转", "onLoginPage" in main_code)
# 断言里统一把单引号折成双引号再匹配：本仓库 TS 用单引号，
# 而写断言时容易顺手写成双引号 —— 那是测试笔误，不该报成代码缺陷。
main_norm = main_code.replace("'", '"')
check("回跳地址限站内（防开放重定向）",
      'startsWith("/")' in main_norm and 'startsWith("//")' in main_norm,
      "需要同时挡掉 //evil.com 这类协议相对 URL")

session_mod = read(WEB / "utils/session.ts")
check("session 模块存在且用事件解耦（避免 http↔store 循环依赖）",
      "CustomEvent" in session_mod and "SESSION_EXPIRED_EVENT" in session_mod)

print("\n=== 前端：路由守卫先续期而不是直接登出 ===")
router_code = strip_comments(read(WEB / "router/index.ts"))
check("守卫调用 ensureValidToken 续期",
      re.search(r"hasUsableToken[\s\S]{0,200}?ensureValidToken", router_code) is not None)
# 旧写法：过期就 clearAuth —— 那等于把 refresh token 当摆设
guard = re.search(r"hasUsableToken[\s\S]{0,200}", router_code)
check("守卫不再直接 clearAuth（改为先尝试续期）",
      bool(guard) and "clearAuth" not in guard.group(0),
      "若这里又出现 clearAuth，说明又变回「一过期就登出」")

print(f"\n{'=' * 60}\n会话续期回归: {ok} 通过 / {bad} 失败\n{'=' * 60}")
sys.exit(1 if bad else 0)
