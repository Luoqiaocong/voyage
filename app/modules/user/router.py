from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute
from app.shared.db.models import User

from .schemas import RegisterUserRequest, LoginUserRequest, UserInfo
from .service import UserService
from .dependencies import get_current_user

router = APIRouter(prefix="/user", tags=["user"], route_class=UnifiedRoute)


@cbv(router)
class UserRouter:
    service: UserService = Depends()

    @router.post("/register", summary="用户注册", status_code=status.HTTP_201_CREATED)
    async def register(self, userdata: RegisterUserRequest):
        await self.service.to_register(userdata.email, userdata.password, userdata.username)

    @router.post("/login", summary="用户登录", status_code=status.HTTP_200_OK)
    async def login(self, userdata: LoginUserRequest):
        token = await self.service.to_login(userdata.email, userdata.password)
        return token

    @router.get("/whoami", summary="获取当前用户信息", status_code=status.HTTP_200_OK, description="测试接口")
    async def whoami(self, current_user: User = Depends(get_current_user)):
        return UserInfo.model_validate(current_user)
