from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute
from app.shared.db.models import User

from .schemas import RegisterUserRequest, LoginUserRequest, UserInfo,UserChangePassWordRequest
from .service import UserService
from .dependencies import get_current_user

router = APIRouter(prefix="/user", tags=["user"], route_class=UnifiedRoute)


# TODO: 
# 1.用户注销
# 2.用户密码更改
# 3.用户密码强校验（测试阶段不做，否则接口不好调试）
# 4.用户信息更改考虑（头像就固定那么几个吧，不要用户上传了；username可更改）
# 5.refresh token的真正实现（需引入redis，稍复杂，后续整个项目功能差不多了再做）


@cbv(router)
class UserRouter:
    service: UserService = Depends()

    @router.post("/reg", summary="用户注册", status_code=status.HTTP_201_CREATED)
    async def register(self, userdata: RegisterUserRequest):
        await self.service.to_register(userdata.email, userdata.password, userdata.username)

    @router.post("/login", summary="用户登录", status_code=status.HTTP_200_OK)
    async def login(self, userdata: LoginUserRequest):
        token = await self.service.to_login(userdata.email, userdata.password)
        return token

    @router.get("/whoami", summary="获取当前用户信息", status_code=status.HTTP_200_OK, description="测试接口")
    async def whoami(self, current_user: User = Depends(get_current_user)):
        return UserInfo.model_validate(current_user)
    
    @router.post("/pwd", summary="用户密码修改", status_code=status.HTTP_200_OK)
    async def change_password(self,pwd_req :UserChangePassWordRequest, current_user: User = Depends(get_current_user),):
        return await self.service.to_change_pwd(current_user.id,pwd_req.current_password, pwd_req.new_password)

    @router.post("/info", summary="用户信息修改", status_code=status.HTTP_200_OK)
    async def change_info(self, current_user: User = Depends(get_current_user)):
        pass
    
    @router.post("/delete", summary="用户注销", status_code=status.HTTP_200_OK)
    async def delete_user(self, current_user: User = Depends(get_current_user)):
        pass