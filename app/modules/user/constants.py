OPTIONAL_AVATARS = [
    "adventure_plaid.png",
    "mountain_bucket.png",
    "photographer.png",
    "navigator_beanie.png",
    "world_explorer.png",
    "nature_botanist.png",
]

AVATAR_BASE_URL = "https://yunimg.heiseven.top/voyage-avatar/"

# ===================== 角色 =====================
#
# 三个角色构成一个简单的层级：
#
#   super_admin  超级管理员 —— 读写全通，可管理用户与其它管理员
#   admin        普通管理员 —— **只读**：能查看后台全部数据，但不能做任何操作
#   user         普通用户
#
# 为什么需要区分两种管理员：
#   单一 admin 档次下所有管理员地位平等，任一管理员都能把另一个管理员
#   降为普通用户 —— 一次误操作就能剥夺同事的权限。
#   分级后，普通管理员看得到数据但动不了任何人，适合给「需要看报表但不该
#   改数据」的角色；超级管理员才具备管理能力。
#
# 为什么普通管理员叫 admin 而不是 viewer：
#   用户明确要求「可以叫管理，但实际上不具备任何管理权限，只有查看权限」。
#   前端的权限判断一律走 can_write（见 ROLE_RANK），不靠角色名推断，
#   因此名字叫 admin 不会带来歧义。
ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"

#: 角色层级，数字越大权限越高。判断「能否操作他人」时一律比对这个值，
#: 而不是枚举角色名——将来加角色时只需在表里加一行。
ROLE_RANK: dict[str, int] = {
    ROLE_USER: 0,
    ROLE_ADMIN: 1,
    ROLE_SUPER_ADMIN: 2,
}

VALID_ROLES = frozenset(ROLE_RANK)

#: 可进入管理端的角色（读权限）。
ADMIN_ROLES = frozenset({ROLE_ADMIN, ROLE_SUPER_ADMIN})


def role_rank(role: str | None) -> int:
    """角色的层级值；未知角色返回 -1。

    取 -1 而不是 0：0 是普通用户的层级，而**未知角色不该被当成普通用户**。
    在 can_manage_role 里 -1 会让「未知角色」永远不可被管理（见下），
    这是刻意的默认拒绝——将来若新增了更高角色却忘了改这里，
    表现是「管理不了」而不是「越权管理得了」。
    """
    return ROLE_RANK.get(role or "", -1)


def is_admin_role(role: str | None) -> bool:
    """是否可进入管理端（含只读的普通管理员）。"""
    return role in ADMIN_ROLES


def can_manage_role(operator_role: str | None, target_role: str | None) -> bool:
    """operator 能否管理 target。

    规则：**只能管理层级严格低于自己的账号**，且双方都必须是已知角色。

    这一条同时解决三件事：
      - 普通管理员不能动任何人（包括降级超级管理员）
      - 超级管理员之间也互相动不了，避免平级互删导致无人可管
      - 未知角色一律不可被管理（默认拒绝）

    最后一点容易被忽略：若只比较层级值，role_rank("unknown") 得到 -1，
    任何已知角色都「大于」它，于是未知角色变成人人都能操作的软柿子。
    而未知角色恰恰可能是将来新增的更高权限角色 —— 所以必须先确认
    它是个已知角色，再比层级。
    """
    if operator_role not in ROLE_RANK or target_role not in ROLE_RANK:
        return False
    return ROLE_RANK[operator_role] > ROLE_RANK[target_role]


# 允许用户自行修改的字段白名单。
#
# 安全要点：PATCH /users/info 走 model_dump(exclude_unset=True) 后映射到 ORM，
# 若把 role / is_active 交给请求体，任何登录用户都能把自己提权为管理员。
# 目前 UserProfileUpdate 恰好只声明了 username/avatar，Pydantic 会丢弃多余字段，
# 所以暂不可利用——但只要有人给 schema 加一个字段，就会立刻变成真漏洞。
# 因此服务层显式按此白名单过滤，角色与启用状态只能经管理端接口或 CLI 变更。
SELF_EDITABLE_FIELDS = frozenset({"username", "avatar"})