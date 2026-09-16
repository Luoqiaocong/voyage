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
ROLE_USER = "user"
ROLE_ADMIN = "admin"
VALID_ROLES = frozenset({ROLE_USER, ROLE_ADMIN})

# 允许用户自行修改的字段白名单。
#
# 安全要点：PATCH /users/info 走 model_dump(exclude_unset=True) 后映射到 ORM，
# 若把 role / is_active 交给请求体，任何登录用户都能把自己提权为管理员。
# 目前 UserProfileUpdate 恰好只声明了 username/avatar，Pydantic 会丢弃多余字段，
# 所以暂不可利用——但只要有人给 schema 加一个字段，就会立刻变成真漏洞。
# 因此服务层显式按此白名单过滤，角色与启用状态只能经管理端接口或 CLI 变更。
SELF_EDITABLE_FIELDS = frozenset({"username", "avatar"})