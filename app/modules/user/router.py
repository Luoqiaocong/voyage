from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute
from app.shared.db.models import User

from .auth import AVATAR_BASE_URL, OPTIONAL_AVATARS
from .dependencies import get_current_user
from .schemas import (
    LoginUserRequest,
    RegisterUserRequest,
    UserChangePassWordRequest,
    UserInfo,
    UserProfileUpdate,
)
from .service import UserService

router = APIRouter(prefix="/user", tags=["user"], route_class=UnifiedRoute)


# TODO: 
# 1.用户注销
# 2.用户密码更改  ✅ 已实现
# 3.用户密码强校验（测试阶段不做，否则接口不好调试）
# 4.用户信息更改考虑（头像就固定那么几个吧，不要用户上传了；username可更改）✅ 已实现
# 5.refresh token的真正实现（需引入redis，稍复杂，后续整个项目功能差不多了再做）


@cbv(router)
class UserRouter:
    service: UserService = Depends()

    @router.get("/avatars", summary="获取可选头像列表", status_code=status.HTTP_200_OK)
    async def get_avatars(self):
        """返回固定头像库（无需登录）：base_url + 短名列表，前端拼接展示。"""
        return {"base_url": AVATAR_BASE_URL, "avatars": OPTIONAL_AVATARS}

    @router.post("/reg", summary="用户注册", status_code=status.HTTP_201_CREATED)
    async def register(self, userdata: RegisterUserRequest):
        
        return await self.service.to_register(userdata.email, userdata.password, userdata.username)

    @router.post("/login", summary="用户登录", status_code=status.HTTP_200_OK)
    async def login(self, userdata: LoginUserRequest):
        return await self.service.to_login(userdata.email, userdata.password)

    @router.get("/info", summary="获取当前用户信息", status_code=status.HTTP_200_OK)
    async def get_info(self, current_user:Annotated[User,Depends(get_current_user)]):
        return UserInfo.model_validate(current_user)
    
    @router.post("/info", summary="用户信息修改", status_code=status.HTTP_200_OK)
    async def change_info(self, update_req:UserProfileUpdate,current_user:Annotated[User,Depends(get_current_user)]):
        return UserInfo.model_validate(
            await self.service.to_change_profile(current_user.id, update_req.model_dump(exclude_unset=True,exclude_none=True)))
        
    @router.post("/pwd", summary="用户密码修改", status_code=status.HTTP_200_OK)
    async def change_password(self,pwd_req :UserChangePassWordRequest, current_user:Annotated[User,Depends(get_current_user)]):
        return await self.service.to_change_pwd(current_user.id,pwd_req.current_password, pwd_req.new_password)

    