from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import config
from app.core.business.code import BusinessCode
from app.core.business.exception import UserException
from app.shared.db.models import User

from .auth import get_real_id
from .repo import UserRepo

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/user/login")


async def _verify_token_logic(token: str, repo: UserRepo) -> User:
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise UserException(code=BusinessCode.TOKEN_EXPIRED)
    except JWTError:
        raise UserException(code=BusinessCode.TOKEN_INVALID)

    user_id = get_real_id(str(payload.get("sub")))
    if not user_id:
        raise UserException(code=BusinessCode.TOKEN_INVALID)

    user = await repo.get_user_dynamic(user_id)
    if not user:
        raise UserException(code=BusinessCode.TOKEN_INVALID)

    return user


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    repo: Annotated[UserRepo, Depends()],
) -> User:
    return await _verify_token_logic(token, repo)
