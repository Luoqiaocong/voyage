from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.business import BusinessCode, UserException
from app.modules.auth.tokens import decode_access_token
from app.shared.db.models import User

from .auth import get_real_id
from .constants import ROLE_SUPER_ADMIN, is_admin_role
from .repo import UserRepo

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")


async def _authenticate_token(token: str, repo: UserRepo) -> User:
    # 认证域：解码校验令牌
    payload = decode_access_token(token)

    if not (sub := payload.get("sub")) or not (user_id := get_real_id(str(sub))):
        raise UserException(code=BusinessCode.TOKEN_INVALID)

    # 用户域：映射并加载用户实体
    user = await repo.get_user_dynamic(user_id)
    if not user:
        raise UserException(code=BusinessCode.TOKEN_INVALID)

    return user


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    repo: Annotated[UserRepo, Depends()],
) -> User:
    return await _authenticate_token(token, repo)


async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """管理端**读取**权限：普通管理员与超级管理员都可进入。

    校验顺序刻意如此：先由 get_current_user 确认令牌有效，再判角色。
    这样「未登录」与「已登录但非管理员」返回不同的业务码，语义不会混淆。

    被停用的账号同样拒绝——即使它历史上是管理员，停用后不应再能操作后台。

    注意这是**只读**入口：所有写操作的接口必须改用 get_current_super_admin，
    否则普通管理员就能改动数据，与「只有查看权限」的定位不符。
    """
    if not is_admin_role(current_user.role):
        raise UserException(code=BusinessCode.PERMISSION_DENIED)
    if not current_user.is_active:
        raise UserException(code=BusinessCode.USER_ACCOUNT_DISABLED)
    return current_user


async def get_current_super_admin(
    current_user: Annotated[User, Depends(get_current_admin)],
) -> User:
    """管理端**写入**权限：仅超级管理员。

    为什么单独抽一个依赖而不是在 service 里判：
      写接口有多个，靠每个函数自己记得判断角色，早晚会漏一个。
      把它做成路由层的依赖，**漏判会直接表现为接口无鉴权**，
      在代码审查与测试中都更容易发现。

    超级管理员同样要求 is_active（由 get_current_admin 链式保证）。
    """
    if current_user.role != ROLE_SUPER_ADMIN:
        raise UserException(
            code=BusinessCode.PERMISSION_DENIED,
            msg="当前账号只有查看权限，无法执行该操作",
        )
    return current_user