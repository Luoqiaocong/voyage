from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.business import BusinessCode, UserException
from app.modules.auth.tokens import decode_access_token
from app.shared.db.models import User

from .auth import get_real_id
from .constants import ROLE_ADMIN
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
    """管理端接口的鉴权依赖：要求当前用户角色为 admin。

    校验顺序刻意如此：先由 get_current_user 确认令牌有效，再判角色。
    这样「未登录」与「已登录但非管理员」返回不同的业务码，语义不会混淆。

    被停用的账号同样拒绝——即使它历史上是管理员，停用后不应再能操作后台。
    """
    if current_user.role != ROLE_ADMIN:
        raise UserException(code=BusinessCode.PERMISSION_DENIED)
    if not current_user.is_active:
        raise UserException(code=BusinessCode.USER_ACCOUNT_DISABLED)
    return current_user