"""API 路由汇总：所有业务模块的 router 在这里聚合，main.py 只挂一个。"""
from fastapi import APIRouter

from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.conversation.router import router as conversation_router
from app.modules.itinerary.router import router as itinerary_router
from app.modules.itinerary.share_router import (
    export_router as itinerary_export_router,
    owner_router as itinerary_share_owner_router,
    public_router as share_public_router,
)
from app.modules.memory.router import router as memory_router
from app.modules.user.router import router as user_router

API_V1_STR = "/api/v1"

api_router = APIRouter()
api_router.include_router(user_router, prefix=API_V1_STR)
api_router.include_router(memory_router, prefix=API_V1_STR)
api_router.include_router(conversation_router, prefix=API_V1_STR)
api_router.include_router(itinerary_router, prefix=API_V1_STR)
# 分享者侧与导出路由都挂在 /itineraries 下，但路径段（shares / export）不与
# 主 router 的 /{id} 冲突：后者的 id 带 gt=0 的整数约束。
api_router.include_router(itinerary_share_owner_router, prefix=API_V1_STR)
api_router.include_router(itinerary_export_router, prefix=API_V1_STR)
api_router.include_router(auth_router, prefix=API_V1_STR)
api_router.include_router(admin_router, prefix=API_V1_STR)
# 公开分享入口：无需登录，刻意放在最后以免影响其他路由匹配
api_router.include_router(share_public_router, prefix=API_V1_STR)