"""管理员分级：权限规则验证。

覆盖三个角色构成的层级，以及「谁能操作谁」的完整规则矩阵。
这类权限逻辑一旦出错就是安全问题，故逐条断言而不是抽样。
"""
import sys

sys.path.insert(0, ".")

from app.modules.user.constants import (
    ADMIN_ROLES,
    ROLE_ADMIN,
    ROLE_RANK,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    VALID_ROLES,
    can_manage_role,
    is_admin_role,
    role_rank,
)

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


print("=== 1. 角色集合 ===")
print(f"  VALID_ROLES = {sorted(VALID_ROLES)}")
check("包含三个角色", VALID_ROLES == {ROLE_USER, ROLE_ADMIN, ROLE_SUPER_ADMIN})
check("层级值递增", ROLE_RANK[ROLE_USER] < ROLE_RANK[ROLE_ADMIN] < ROLE_RANK[ROLE_SUPER_ADMIN])
check("ADMIN_ROLES 含两种管理员", ADMIN_ROLES == {ROLE_ADMIN, ROLE_SUPER_ADMIN})

print("\n=== 2. 能否进入管理端（读权限）===")
for role, want in [
    (ROLE_SUPER_ADMIN, True),
    (ROLE_ADMIN, True),
    (ROLE_USER, False),
    (None, False),
    ("unknown_role", False),
]:
    got = is_admin_role(role)
    check(f"is_admin_role({role!r}) = {want}", got == want, str(got))

print("\n=== 3. 未知角色按最低权限处理（默认拒绝而非放行）===")
check("role_rank(None) 为负", role_rank(None) < 0, str(role_rank(None)))
check("role_rank('hacker') 为负", role_rank("hacker") < 0, str(role_rank("hacker")))
check("未知角色不能进入管理端", not is_admin_role("hacker"))

print("\n=== 4. can_manage_role 完整矩阵 ===")
# (operator, target, 期望值, 说明)
MATRIX = [
    (ROLE_SUPER_ADMIN, ROLE_USER, True, "超管可管理普通用户"),
    (ROLE_SUPER_ADMIN, ROLE_ADMIN, True, "超管可管理普通管理员（含降级）"),
    (ROLE_SUPER_ADMIN, ROLE_SUPER_ADMIN, False, "超管之间互不可动（防内耗）"),
    (ROLE_ADMIN, ROLE_USER, True, "普通管理员可管理普通用户"),
    (ROLE_ADMIN, ROLE_ADMIN, False, "普通管理员不能动同级"),
    (ROLE_ADMIN, ROLE_SUPER_ADMIN, False, "**普通管理员不能降级超管**（用户报的问题）"),
    (ROLE_USER, ROLE_USER, False, "普通用户不能动同级"),
    (ROLE_USER, ROLE_ADMIN, False, "普通用户不能动管理员"),
    (ROLE_USER, ROLE_SUPER_ADMIN, False, "普通用户不能动超管"),
    (ROLE_ADMIN, "unknown", False, "未知目标角色视为更高（拒绝）"),
    ("unknown", ROLE_USER, False, "未知操作者角色视为最低（拒绝）"),
]
for op, tgt, want, why in MATRIX:
    got = can_manage_role(op, tgt)
    check(f"{op:<12} -> {tgt:<12} = {got}   （{why}）", got == want, f"期望 {want}")

print("\n=== 5. 关键结论 ===")
# 用户明确报的问题：普通管理员能把超管降为用户
check("普通管理员无法降级超管",
      not can_manage_role(ROLE_ADMIN, ROLE_SUPER_ADMIN))
# 用户要求：普通管理员「不具备任何管理权限，只有查看权限」
# —— 它仍可管理普通用户（角色变更），但下面这条检查的是它不能碰管理员
check("普通管理员碰不到任何管理员",
      not can_manage_role(ROLE_ADMIN, ROLE_ADMIN)
      and not can_manage_role(ROLE_ADMIN, ROLE_SUPER_ADMIN))
check("普通管理员仍可查看后台（读权限）", is_admin_role(ROLE_ADMIN))

print(f"\n{'=' * 60}\n角色权限验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 60}")
sys.exit(1 if fail_n else 0)
