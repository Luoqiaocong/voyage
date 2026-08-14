from typing import Any, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .code import BusinessCode


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
    message: Optional[str] = None,
    data: Any = None,
) -> JSONResponse:
    """成功响应"""
    return _base_response(
        status_code=status_code,
        business_code=business_code.code,
        message=message or business_code.message,
        data=data,
    )