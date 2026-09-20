"""验证 MCP 启动命令在 Windows 与 Linux 上都正确。

不能只在当前平台测 —— 当前是 Windows，生成的一定是 cmd 形式，
而 Linux 形式（本改动要修的那条路径）必须靠模拟才能覆盖。
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, ".")

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def load(platform: str):
    """把 sys.platform 改成目标值后重新导入模块，取得该平台下的配置。"""
    import app.core.ai.mcp as mod

    original = sys.platform
    sys.platform = platform
    try:
        importlib.reload(mod)
        return mod
    finally:
        sys.platform = original


print("=== 1. Windows 下生成的命令 ===")
w = load("win32")
ddg_w = w.MCPCONFIG["TRAVEL_TOOLS_CONFIG"]["duckduckgo-mcp-server"]
print(f"  command={ddg_w['command']!r}  args={ddg_w['args']}")
check("Windows 用 cmd", ddg_w["command"] == "cmd")
check("Windows 带 /c", ddg_w["args"][0] == "/c")
check("Windows 能拿到 uvx", "uvx" in ddg_w["args"])
check("Windows 不缺包名", any("duckduckgo-mcp-server" in a for a in ddg_w["args"]))

print("\n=== 2. Linux 下生成的命令（本次修复的核心）===")
lin = load("linux")
ddg_l = lin.MCPCONFIG["TRAVEL_TOOLS_CONFIG"]["duckduckgo-mcp-server"]
print(f"  command={ddg_l['command']!r}  args={ddg_l['args']}")
check("Linux 直接调 uvx，不用 cmd", ddg_l["command"] == "uvx", ddg_l["command"])
check("Linux 不传 /c", "/c" not in ddg_l["args"], str(ddg_l["args"]))
check("Linux 缺包名", any("duckduckgo-mcp-server" in a for a in ddg_l["args"]))

print("\n=== 3. 版本固定（可复现）===")
# 从模块常量读取，而不是把版本号写死在测试里 ——
# 否则每次升级版本都要改测试，漏改就会造成假失败
import app.core.ai.mcp as _m

print(f"  配置固定版本: {_m._DDG_MCP_PACKAGE}")
check("包名正确", _m._DDG_MCP_PACKAGE.startswith("duckduckgo-mcp-server=="),
      _m._DDG_MCP_PACKAGE)
check("版本号非空", len(_m._DDG_MCP_PACKAGE.split("==")[1]) > 0)
check("Windows args 用的是同一常量", _m._DDG_MCP_PACKAGE in ddg_w["args"], str(ddg_w["args"]))
check("Linux args 用的是同一常量", _m._DDG_MCP_PACKAGE in ddg_l["args"], str(ddg_l["args"]))

print("\n=== 4. 其余 MCP 不受平台影响（都是远程 HTTP）===")
for platform in ("win32", "linux"):
    m = load(platform)
    transports = {
        name: cfg["transport"]
        for cfg in m.MCPCONFIG.values()
        for name, cfg in cfg.items()
    }
    http_only = {n for n, t in transports.items() if t != "stdio"}
    check(f"{platform}: 除 ddg 外全为远程传输", len(http_only) == 5,
          f"{len(http_only)} 个远程 / 共 {len(transports)} 个")

print("\n=== 5. 当前平台实际生效的配置 ===")
import app.core.ai.mcp as current

importlib.reload(current)
now = current.MCPCONFIG["TRAVEL_TOOLS_CONFIG"]["duckduckgo-mcp-server"]
print(f"  sys.platform={sys.platform!r}  ->  command={now['command']!r} args={now['args']}")
expected = "cmd" if sys.platform == "win32" else "uvx"
check("当前平台命令正确", now["command"] == expected, now["command"])

print("\n=== 6. 超时配置（冷启动 vs 运行期）===")
# 为什么必须锁住这组值：
# 冷启动要额外承担 uvx 下载包 + 与 checkpointer/Redis 初始化争 CPU，
# 实测首次 11.47s、缓存预热后 4.08s。若把冷启动超时调回 10s，
# **全新部署第一次启动必然判超时**，travel 子 Agent 静默降级为 0 个工具 ——
# 用户侧只看到「搜索/酒店/美食没数据」，没有任何报错，极难排查。
cold = current.COLD_START_TIMEOUT_SECONDS
warm = current.TOOL_FETCH_TIMEOUT_SECONDS
check("冷启动超时存在", isinstance(cold, (int, float)), str(cold))
check("运行期超时存在", isinstance(warm, (int, float)), str(warm))
check("冷启动超时显著大于运行期超时（两级策略生效）",
      cold >= warm * 2, f"cold={cold} warm={warm}")
check("冷启动超时足以覆盖实测首次耗时 11.47s",
      cold >= 30, f"cold={cold}s（实测首次 11.47s）")
check("运行期超时仍收得够短（不被慢端点拖住）",
      warm <= 20, f"warm={warm}s")
check("有 warmed 集合用于区分冷启动/运行期",
      hasattr(current, "_warmed_namespaces"))

src = Path("app/core/ai/mcp.py").read_text(encoding="utf-8")
check("超时按 cold 变量选择（而非写死一个值）",
      "COLD_START_TIMEOUT_SECONDS if cold else TOOL_FETCH_TIMEOUT_SECONDS" in src)
check("失败日志带上冷启动/运行期与超时值（便于排查）",
      "冷启动" in src and "超时" in src)

print(f"\n{'=' * 56}\nMCP 平台兼容验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
sys.exit(1 if fail_n else 0)
