from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status
from app.core.route import UnifiedRoute
from .service import UserService
from .schemas import RegisterUserRequest, LoginUserRequest
router = APIRouter(prefix="/user", tags=["user"],route_class=UnifiedRoute)

@cbv(router)
class UserPublicRouter:
    service : UserService = Depends()
    
    @router.post("/register", summary="用户注册", status_code=status.HTTP_201_CREATED)
    async def register(self, userdata: RegisterUserRequest):
        await self.service.to_register(userdata.email,userdata.password,userdata.username)

    @router.post("/login", summary="用户登录", status_code=status.HTTP_200_OK)
    async def login(self, userdata: LoginUserRequest):
        token = await self.service.to_login(userdata.email,userdata.password)
        return token
    

