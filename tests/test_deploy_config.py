"""部署文件静态校验。

没有 Docker 环境，但以下几类问题可以静态查出来，且它们恰好是
「上服务器才发现」的高频原因：
  - compose 叠加文件的合并语义是否正确（ports: !reset 是否生效）
  - Caddyfile 引用的环境变量是否都在 compose 里注入
  - 反代目标主机名是否与 compose 服务名一致（写 localhost 是最常见错误）
  - .env.example 是否覆盖了 config.py 的必填项
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

try:
    import yaml
except ImportError:
    print("需要 pyyaml")
    sys.exit(2)


# !reset / !override 是 Docker Compose 的合并指令，PyYAML 不认这两个标签。
# 注册为空标签构造器，让文档能被解析——识别不了标签并不代表 YAML 有问题，
# 反而是「确实用了 compose 专有指令」的证据（下面会单独断言）。
class _ComposeTag:
    def __init__(self, value):
        self.value = value

    def __repr__(self) -> str:
        return f"!reset/!override({self.value!r})"


def _tag_ctor(loader, node):
    if isinstance(node, yaml.SequenceNode):
        return _ComposeTag(loader.construct_sequence(node))
    if isinstance(node, yaml.MappingNode):
        return _ComposeTag(loader.construct_mapping(node))
    return _ComposeTag(loader.construct_scalar(node))


yaml.SafeLoader.add_constructor("!reset", _tag_ctor)
yaml.SafeLoader.add_constructor("!override", _tag_ctor)

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


base = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
tls = yaml.safe_load(Path("deploy/docker-compose.tls.yml").read_text(encoding="utf-8"))
caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")

print("=== 1. 叠加文件本身可解析且结构正确 ===")
check("deploy/docker-compose.tls.yml 是合法 YAML", isinstance(tls, dict))
check("含 caddy 服务", "caddy" in tls.get("services", {}))
check("主 compose 未被改动结构", "web" in base["services"] and "backend" in base["services"])

print("\n=== 2. 端口不冲突（这是叠加层最容易错的地方）===")
web_ports = tls["services"]["web"].get("ports")
# compose 的 !reset 在 YAML 里表现为自定义标签，解析后是 _ComposeTag 包装的 []
print(f"  叠加文件中 web.ports = {web_ports!r}")
_inner = getattr(web_ports, "value", web_ports)
check("web 的 80 端口已被重置（否则与 Caddy 抢 80）",
      _inner == [] or web_ports is None, repr(web_ports))
# 原始文本里确认用的是 !reset 而不是空列表（空列表在某些 compose 版本不生效）
raw_tls = Path("deploy/docker-compose.tls.yml").read_text(encoding="utf-8")
check("重置用的是 !reset 指令（空列表不可靠）", "ports: !reset" in raw_tls)

caddy_ports = tls["services"]["caddy"].get("ports", [])
print(f"  caddy.ports = {caddy_ports}")
check("Caddy 占用 80", any("80:80" in str(p) for p in caddy_ports))
check("Caddy 占用 443", any(str(p).startswith("443:443") for p in caddy_ports))

print("\n=== 3. 网络一致（不同网络会导致 DNS 解析不到服务名）===")
base_nets = set((base.get("networks") or {}).keys())
tls_caddy_nets = set(tls["services"]["caddy"].get("networks") or [])
print(f"  主 compose networks = {base_nets}")
print(f"  caddy networks      = {tls_caddy_nets}")
check("Caddy 与主 compose 在同一网络", tls_caddy_nets <= base_nets,
      f"{tls_caddy_nets} vs {base_nets}")

print("\n=== 4. 反代目标主机名正确 ===")
m = re.search(r"reverse_proxy\s+(\S+)", caddyfile)
target = m.group(1) if m else None
print(f"  Caddyfile reverse_proxy 目标 = {target}")
check("目标是 web 服务名而非 localhost",
      target is not None and target.startswith("web:"),
      target or "未找到")
check("端口为 80（nginx 监听 80）", target is not None and target.endswith(":80"), target or "")
# 与主 compose 的 web 服务名对齐
check("web 确在主 compose 中", "web" in base["services"])

print("\n=== 5. Caddyfile 引用的环境变量都已注入 ===")
used_vars = set(re.findall(r"\{\$([A-Z_]+)\}", caddyfile))
injected = set(tls["services"]["caddy"].get("environment") or {})
print(f"  Caddyfile 用到   = {sorted(used_vars)}")
print(f"  compose 注入     = {sorted(injected)}")
missing = used_vars - injected
check("无遗漏的环境变量", not missing, f"缺少 {sorted(missing)}" if missing else "")

print("\n=== 6. 必填变量有校验（未设置应直接失败而非静默降级）===")
for var in ("DOMAIN", "ACME_EMAIL"):
    raw = str((tls["services"]["caddy"].get("environment") or {}).get(var, ""))
    check(f"{var} 使用 :? 强制校验", ":?" in raw, raw[:70])

print("\n=== 7. 证书持久化（否则重建容器会重复申请，触发 LE 限流）===")
vols = tls["services"]["caddy"].get("volumes", [])
check("挂载了 /data", any("/data" in str(v) for v in vols), str(vols))
check("挂载了 /config", any("/config" in str(v) for v in vols), str(vols))
check("caddy-data 卷已声明", "caddy-data" in (tls.get("volumes") or {}))
check("caddy-config 卷已声明", "caddy-config" in (tls.get("volumes") or {}))

print("\n=== 8. Caddyfile 语法要点 ===")
# 去掉注释行后再看首个有效字符——Caddyfile 通常以注释头开头
caddy_code = "\n".join(
    line for line in caddyfile.splitlines() if not line.strip().startswith("#")
)
check("有全局配置块", caddy_code.lstrip().startswith("{"),
      repr(caddy_code.lstrip()[:20]))
check("site 地址用 {$DOMAIN}", "{$DOMAIN}" in caddyfile)
check("关闭缓冲（SSE 流式必需）", "flush_interval -1" in caddyfile,
      "缺失会导致 AI 回复整段蹦出")
check("有 HSTS 头", "Strict-Transport-Security" in caddyfile)
check("大括号配平", caddyfile.count("{") == caddyfile.count("}"),
      f"{caddyfile.count('{')} vs {caddyfile.count('}')}")
# 版本写在 image 里而不是 latest，便于复现
check("Caddy 镜像固定版本（非 latest）",
      re.search(r"image: caddy:\d+\.\d+", raw_tls) is not None,
      (re.search(r"image: caddy:\S+", raw_tls) or [""])[0] if re.search(r"image: caddy:\S+", raw_tls) else "")

print("\n=== 9. nginx 侧也关了缓冲（两层都不能缓冲）===")
nginx = Path("web/nginx.conf").read_text(encoding="utf-8")
check("proxy_buffering off", "proxy_buffering off" in nginx)
check("长超时（AI 生成可能很久）", "proxy_read_timeout 600s" in nginx)
check("SPA 回退存在", "try_files $uri $uri/ /index.html" in nginx)

print("\n=== 10. .env.example 与 config.py 的必填项一致 ===")
from app.config import config  # noqa: E402

src = Path("app/config.py").read_text(encoding="utf-8")
required = re.findall(r"^\s{4}([A-Z][A-Z0-9_]*):\s*[^=\n]+$", src, re.M)
example = Path(".env.example").read_text(encoding="utf-8")
missing_env = [k for k in required if k not in example]
print(f"  config 必填 {len(required)} 项，示例缺失: {missing_env or '无'}")
check("示例覆盖全部必填项", not missing_env)

print("\n=== 11. 部署文档与配置文件是否一致 ===")
runbook = Path("deploy/RUNBOOK.md").read_text(encoding="utf-8")
check("RUNBOOK 提到叠加文件路径", "deploy/docker-compose.tls.yml" in runbook)
check("RUNBOOK 提到 Caddyfile", "deploy/Caddyfile" in runbook)
check("RUNBOOK 警告了 down -v 的风险", "down -v" in runbook)
check("RUNBOOK 说明首个用户即管理员", "第一个注册用户即管理员" in runbook or "首个" in runbook)
# 文档里不该出现写死的域名（占位符形如 <你的域名>）。
# 排除已知的工具站点：它们出现在安装命令里是正常的，不是「写死的部署域名」。
KNOWN_TOOL_HOSTS = {"get.docker.com", "github.com", "docs.docker.com",
                    "pypi.org", "hub.docker.com"}
hardcoded = [
    h for h in re.findall(r"https://([a-z0-9.-]+\.(?:com|cn|net|io|org))\b", runbook)
    if h not in KNOWN_TOOL_HOSTS and "example" not in h
]
if hardcoded:
    warn("RUNBOOK 里出现了疑似写死的域名", str(sorted(set(hardcoded))))
else:
    check("RUNBOOK 未写死部署域名（用占位符）", True)

print(f"\n{'=' * 60}")
print(f"部署文件校验: {ok_n} 通过 / {fail_n} 失败 / {warn_n} 警告")
print(f"{'=' * 60}")
sys.exit(1 if fail_n else 0)
