from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from starlette import status

from app.core.route import UnifiedRoute
from app.shared.ratelimit import (
    CODE_IP_LIMIT,
    CODE_IP_WINDOW,
    RESET_IP_LIMIT,
    RESET_IP_WINDOW,
    rate_limit,
)

from .schemas import AccessTokenRequest, EmailCodeRequest, VerifyEmailRequest
from .service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"], route_class=UnifiedRoute)


@cbv(router)
class AuthRouterAPI:

    service: AuthService = Depends()

    @router.post("/code", status_code=status.HTTP_200_OK, summary="颁发Code", dependencies=[Depends(rate_limit("send_code", CODE_IP_LIMIT, CODE_IP_WINDOW))])
    async def send_code(self, verify_req: VerifyEmailRequest):
        return await self.service.send_code(verify_req.email)

    @router.post("/reset-token", status_code=status.HTTP_200_OK, summary="颁发ResetToken", dependencies=[Depends(rate_limit("reset_token", RESET_IP_LIMIT, RESET_IP_WINDOW))])
    async def reset_token(self, req: EmailCodeRequest):
        return await self.service.issue_reset_token(req.email, req.code)
    
    @router.post("/refresh", status_code=status.HTTP_200_OK, summary="颁发AccessToken")
    async def access_token(self, req: AccessTokenRequest):
        return await self.service.issue_access_token(req.refresh_token)
    
