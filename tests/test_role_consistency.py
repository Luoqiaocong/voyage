"""前后端角色定义一致性校验。

本次出错的根源：后端引入了 super_admin，前端 4 处判断仍只认 'admin'，
导致超管「后端放行但界面看不到入口」。这类漂移靠人工检查很容易漏，
故用测试锁住两件事：
  1. 两端的角色集合与层级完全一致
  2. 前端源码里不再出现写死的 role === 'admin' 判断
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


print("=== 1. 后端角色定义 ===")
from app.modules.user.constants import (  # noqa: E402
    ADMIN_ROLES,
    ROLE_RANK,
    VALID_ROLES,
)

print(f"  ROLE_RANK   = {ROLE_RANK}")
print(f"  VALID_ROLES = {sorted(VALID_ROLES)}")
print(f"  ADMIN_ROLES = {sorted(ADMIN_ROLES)}")
check("角色集合有三级", VALID_ROLES == {"user", "admin", "super_admin"})
check("层级严格递增",
      ROLE_RANK["user"] < ROLE_RANK["admin"] < ROLE_RANK["super_admin"])
check("两种管理员都能进后台", ADMIN_ROLES == {"admin", "super_admin"})

print("\n=== 2. 前端 utils/role.ts 的定义 ===")
fe = Path("web/src/utils/role.ts").read_text(encoding="utf-8")

m = re.search(r"ROLE_RANK:\s*Record<string,\s*number>\s*=\s*\{([\s\S]*?)\}", fe)
check("找到 ROLE_RANK", m is not None)
fe_rank: dict[str, int] = {}
if m:
    for name, val in re.findall(r"(\w+):\s*(\d+)", m.group(1)):
        fe_rank[name] = int(val)
print(f"  前端 ROLE_RANK = {fe_rank}")

check("前后端 ROLE_RANK 完全一致",
      fe_rank == dict(ROLE_RANK),
      f"前端 {fe_rank} vs 后端 {dict(ROLE_RANK)}")

# canAccessAdmin 的阈值必须等于 admin 的层级
m2 = re.search(r"canAccessAdmin[\s\S]{0,200}?roleRank\(role\)\s*>=\s*ROLE_RANK\.(\w+)", fe)
check("canAccessAdmin 阈值为 admin", m2 is not None and m2.group(1) == "admin",
      m2.group(1) if m2 else "未匹配")
m3 = re.search(r"canWriteAdmin[\s\S]{0,200}?roleRank\(role\)\s*>=\s*ROLE_RANK\.(\w+)", fe)
check("canWriteAdmin 阈值为 super_admin",
      m3 is not None and m3.group(1) == "super_admin",
      m3.group(1) if m3 else "未匹配")

print("\n=== 3. 前端不再有写死的单角色判断 ===")
# 注释里提到是允许的（说明历史原因），只看真实代码
violations: list[str] = []
for f in Path("web/src").rglob("*"):
    if f.suffix not in (".vue", ".ts") or "role.ts" in f.name:
        continue
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("//")[0]
        if code.strip().startswith("*") or code.strip().startswith("/*"):
            continue
        # role === 'admin' / role !== 'admin' 这类单角色判断
        if re.search(r"role\s*[!=]==?\s*'admin'", code):
            # AdminUsers 的三档循环里是合法用法：它按当前角色决定下一个角色
            if "setRole(" in code or "设为管理员" in code:
                continue
            violations.append(f"{f}:{i}  {line.strip()[:80]}")

if violations:
    check("无写死的单角色判断", False, "\n      ".join(violations))
else:
    check("无写死的单角色判断（已收敛到 canAccessAdmin/canWriteAdmin）", True)

print("\n=== 4. 关键文件确实用了共享判断 ===")
targets = {
    "web/src/components/AppNavbar.vue": "canAccessAdmin",
    "web/src/router/index.ts": "canAccessAdmin",
    "web/src/views/ProfileView.vue": "canAccessAdmin",
}
for path, fn in targets.items():
    src = Path(path).read_text(encoding="utf-8")
    check(f"{Path(path).name} 使用 {fn}", fn in src)

print(f"\n{'=' * 60}\n角色定义一致性: {ok_n} 通过 / {fail_n} 失败\n{'=' * 60}")
sys.exit(1 if fail_n else 0)
