from fastapi import APIRouter
from app.modules.user.service import auth_service
from app.modules.user.schemas import AuthRequest, AuthResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthResponse)
async def login(req: AuthRequest):
    token, user_id = await auth_service.login(req.username, req.password)
    return AuthResponse(token=token, user_id=user_id)