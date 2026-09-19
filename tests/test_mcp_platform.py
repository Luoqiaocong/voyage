"""验证 MCP 启动命令在 Windows 与 Linux 上都正确。

不能只在当前平台测 —— 当前是 Windows，生成的一定是 cmd 形式，
而 Linux 形式（本改动要修的那条路径）必须靠模拟才能覆盖。
"""
import importlib
import sys

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

print(f"\n{'=' * 56}\nMCP 平台兼容验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
sys.exit(1 if fail_n else 0)
