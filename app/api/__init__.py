"""API 汇总：路由统一从这里暴露（main.py 只挂一个）。"""
from .router import API_V1_STR, api_router

__all__ = ["API_V1_STR", "api_router"]