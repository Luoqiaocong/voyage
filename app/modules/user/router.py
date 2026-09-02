from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.business import BusinessCode, success_response
from app.core.route import UnifiedRoute
from app.shared.db.models import User

from .constants import AVATAR_BASE_URL, OPTIONAL_AVATARS
from .dependencies import get_current_user
from .schemas import (
    LoginUserRequest,
    RegisterUserRequest,
    UserChangePasswordRequest,
    UserInfo,
    UserProfileUpdate,
    UserRefreshTokenRequest,
    UserResetPasswordRequest,
)
from .service import UserService

router = APIRouter(prefix="/users", tags=["users"], route_class=UnifiedRoute)

# TODO:
# 1. 用户注销 ✅ 已实现
# 2. 用户密码更改 ✅ 已实现
# 3. 用户密码强校验（测试阶段不做，否则接口不好调试） ✅ 已实现
# 4. 用户信息更改考虑（头像固定，用户名可改）✅ 已实现
# 5. Refresh Token 真正实现（需引入 Redis，稍复杂，后续再做）


@cbv(router)
class UserRouter:
    service: UserService = Depends()

    # ============ 公共资源 ============
    @router.get("/avatars", summary="获取可选头像列表", status_code=status.HTTP_200_OK)
    async def get_avatars(self):
        """返回固定头像库（无需登录）：base_url + 短名列表，前端拼接展示。"""
        return {"base_url": AVATAR_BASE_URL, "avatars": OPTIONAL_AVATARS}

    # ============ 认证相关 ============
    @router.post("/reg", summary="用户注册", status_code=status.HTTP_201_CREATED)
    async def register(self, userdata: RegisterUserRequest):
        return await self.service.to_register(
            userdata.email,
            userdata.password,
            userdata.username,
            userdata.code,
        )

    @router.post("/login", summary="用户登录", status_code=status.HTTP_200_OK)
    async def login(self, userdata: LoginUserRequest):
        return await self.service.to_login(userdata.email, userdata.password)

    # ============ 用户信息（需认证） ============
    @router.get("/info", summary="获取当前用户信息", status_code=status.HTTP_200_OK)
    async def get_info(
        self,
        current_user: Annotated[User, Depends(get_current_user)],
    ):
        return UserInfo.model_validate(current_user)

    @router.patch("/info", summary="用户信息修改", status_code=status.HTTP_200_OK)
    async def change_info(
        self,
        update_req: UserProfileUpdate,
        current_user: Annotated[User, Depends(get_current_user)],
    ):
        updated_user_info = UserInfo.model_validate(
            await self.service.to_change_profile(
                current_user.id,
                update_req.model_dump(exclude_unset=True, exclude_none=True),
            ),
        )
        return success_response(
            business_code=BusinessCode.UPDATED,
            data=updated_user_info,
        )

    @router.put("/pwd", summary="用户密码修改", status_code=status.HTTP_204_NO_CONTENT)
    async def change_password(
        self,
        pwd_req: UserChangePasswordRequest,
        current_user: Annotated[User, Depends(get_current_user)],
    ):
        
        return await self.service.to_change_pwd(
            current_user.id,
            pwd_req.current_password,
            pwd_req.new_password,
        )
        
    @router.post("/reset", summary="用户密码重置", status_code=status.HTTP_204_NO_CONTENT)
    async def reset_password(self, reset_req: UserResetPasswordRequest):
        return await self.service.to_reset_pwd(reset_req.password,reset_req.token)
    
    @router.post("/logout", summary="用户登出", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        self,
        token_req: UserRefreshTokenRequest,
        current_user: Annotated[User, Depends(get_current_user)],
    ):
        await self.service.to_logout(token_req.refresh_token,current_user.id)
        
    @router.delete("/", summary="用户注销", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_user(
        self,
        current_user: Annotated[User, Depends(get_current_user)],
    ):
        await self.service.to_delete_user(current_user.id)
