from typing import Annotated
from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status
from .service import AuthService
from .schemas import VerifyEmailRequest
from app.core.route import UnifiedRoute


router = APIRouter(prefix="/auth",tags=['auth'], route_class=UnifiedRoute)

@cbv(router)
class AuthRouterAPI:

    service: AuthService = Depends()

    @router.post('/code',
                 status_code=status.HTTP_200_OK,
                 summary='发送验证码')
    async def send_code(self,verify_req:VerifyEmailRequest):
        return await self.service.send_code(verify_req.email)



