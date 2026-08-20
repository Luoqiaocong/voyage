from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .code import BusinessCode
from .exception import BaseBusinessException


def _base_response(
    status_code: int,
    business_code: int,
    message: str,
    data: Any = None,
) -> JSONResponse:
    """底层统一响应封装"""
    return JSONResponse(
        status_code=status_code,
        content={
            "code": business_code,
            "message": message,
            "data": jsonable_encoder(data),
        },
    )

def success_response(
    status_code: int = 200,
    business_code: BusinessCode = BusinessCode.SUCCESS,
    message: str | None = None,
    data: Any = None,
) -> JSONResponse:
    """成功响应"""
    return _base_response(
        status_code=status_code,
        business_code=business_code.code,
        message=message or business_code.message,
        data=data,
    )
    
    

def register_exception(app: FastAPI):
    """
    全局异常注册函数
    """

    # 1. 处理业务逻辑异常
    @app.exception_handler(BaseBusinessException)
    async def unified_business_exception_handler(request: Request, exc: BaseBusinessException):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "code": exc.code,
                "message": exc.msg,
                "data": exc.data,
            }
        )

    # 2. 处理 FastAPI/Starlette 标准 HTTP 异常
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        error_code_map = {
            401: BusinessCode.UNAUTHORIZED,
            403: BusinessCode.FORBIDDEN,
            404: BusinessCode.NOT_FOUND,
            413: BusinessCode.FILE_TOO_LARGE,
            500: BusinessCode.INTERNAL_ERROR,
        }

        response_code = error_code_map.get(exc.status_code, BusinessCode.INTERNAL_ERROR)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": response_code.code,
                "message": exc.detail,
                "data": None
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if not errors:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "code": BusinessCode.PARAM_ERROR.code,
                    "message": "Param Error",
                    "data": None,
                },
            )
        first_err = errors[0]
        loc = first_err.get("loc") or ()
        field_name = str(loc[-1]) if loc else "unknown"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,  # 或保持 200，团队统一即可
            content={
                "code": BusinessCode.PARAM_ERROR.code,
                "message": "Param Error",
                "data": {"field": field_name, "detail": first_err.get("msg")},
            },
        )


    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # logger.exception("unhandled error: %s", request.url)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": BusinessCode.INTERNAL_ERROR.code,
                "message": "服务器开小差了，请稍后再试",
                "data": str(exc) if getattr(app.state, "debug", False) or getattr(app, "debug", False) else None,
            },
        )