from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.business import BusinessCode, UserException
from app.modules.auth.tokens import decode_access_token
from app.shared.db.models import User

from .auth import get_real_id
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