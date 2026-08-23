"""API 路由汇总：所有业务模块的 router 在这里聚合，main.py 只挂一个。"""
from fastapi import APIRouter

from app.modules.user.router import router as user_router
from app.modules.conversation.router import router as conversation_router
from app.modules.itinerary.router import router as itinerary_router

API_V1_STR = "/api/v1"

api_router = APIRouter()
api_router.include_router(user_router, prefix=API_V1_STR)
api_router.include_router(conversation_router, prefix=API_V1_STR)
api_router.include_router(itinerary_router, prefix=API_V1_STR)