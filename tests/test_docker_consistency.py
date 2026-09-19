"""Docker 部署一致性校验。

没有 Docker 环境时的替代手段：静态校验 Dockerfile 的关键点，
重点是**防止「构建期预热的版本」与「运行期拉起的版本」漂移** ——
Dockerfile 与 app/core/ai/mcp.py 各有一份默认值，必须一致。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

ok_n = fail_n = warn_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def warn(label: str, detail: str = "") -> None:
    global warn_n
    warn_n += 1
    print(f"  [WARN] {label}" + (f" — {detail}" if detail else ""))


docker = Path("Dockerfile").read_text(encoding="utf-8")
compose = Path("docker-compose.yml").read_text(encoding="utf-8")

print("=== 1. 运行阶段是否具备 uvx（stdio MCP 的启动依赖）===")
runtime = docker.split("AS runtime", 1)[1] if "AS runtime" in docker else docker
check("运行阶段 COPY 了 uvx", re.search(r"COPY --from=\S+ /uvx /bin/", runtime) is not None)
check("运行阶段 COPY 了 .venv",
      "--from=builder /app/.venv /app/.venv" in runtime)

print("\n=== 2. 版本单一事实来源 ===")
m = re.search(r"ARG DDG_MCP_PACKAGE=(\S+)", docker)
check("Dockerfile 用 ARG 定义版本", m is not None, m.group(1) if m else "未找到")
docker_ver = m.group(1) if m else None

check("Dockerfile 用 ENV 传给应用",
      re.search(r"ENV DDG_MCP_PACKAGE=\$\{DDG_MCP_PACKAGE\}", docker) is not None)
check("构建期预热用的是同一变量",
      'uvx "${DDG_MCP_PACKAGE}"' in docker)

# 应用侧默认值
from app.core.ai.mcp import _DDG_MCP_PACKAGE  # noqa: E402

app_ver = _DDG_MCP_PACKAGE
print(f"  Dockerfile 版本: {docker_ver}")
print(f"  应用侧默认版本:  {app_ver}")
check("两边版本号一致（防漂移）", docker_ver == app_ver,
      f"{docker_ver} vs {app_ver}")

print("\n=== 3. 预热不能静默失败 ===")
warm = re.search(r"RUN uvx \"\$\{DDG_MCP_PACKAGE\}\" --help[^\n]*", docker)
check("找到预热命令", warm is not None)
if warm:
    check("预热未用 `|| true` 掩盖失败", "|| true" not in warm.group(0),
          warm.group(0))
    check("预热在 USER voyage 之后（缓存归属正确）",
          docker.index("USER voyage") < docker.index("RUN uvx"), "顺序正确")

print("\n=== 4. compose 是否会用 .env 覆盖掉版本 ===")
unsets = []
if "DDG_MCP_PACKAGE" in compose:
    unsets.append("docker-compose.yml")
if Path(".env").exists() and "DDG_MCP_PACKAGE" in Path(".env").read_text(encoding="utf-8"):
    unsets.append(".env")
if unsets:
    warn(f"{unsets} 中出现了 DDG_MCP_PACKAGE，会覆盖 Dockerfile 的 ENV",
         "若是有意为之可忽略")
else:
    check("Dockerfile 的 ENV 不会被 compose/.env 覆盖", True)

print("\n=== 5. 应用侧读取逻辑 ===")
src = Path("app/core/ai/mcp.py").read_text(encoding="utf-8")
check("通过环境变量读取（可被构建期注入）",
      'os.getenv("DDG_MCP_PACKAGE"' in src)
check("有默认值（本地开发无需配置）",
      re.search(r'os\.getenv\("DDG_MCP_PACKAGE",\s*"duckduckgo-mcp-server==', src)
      is not None)

print("\n=== 6. 平台命令生成 ===")
check("Windows 走 cmd", '["cmd", "/c", "uvx"] if _IS_WINDOWS' in src)
check("非 Windows 直接用 uvx", 'else ["uvx"]' in src)

print(f"\n{'=' * 58}")
print(f"Docker 一致性校验: {ok_n} 通过 / {fail_n} 失败 / {warn_n} 警告")
print(f"{'=' * 58}")
sys.exit(1 if fail_n else 0)
