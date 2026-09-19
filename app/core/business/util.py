from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.utils import log

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
            429: BusinessCode.RATE_LIMIT_EXCEEDED,  # 限流触发：HTTP 429 → 业务码
            500: BusinessCode.INTERNAL_ERROR,
        }

        response_code = error_code_map.get(exc.status_code, BusinessCode.INTERNAL_ERROR)

        # 限流等场景可能携带 Retry-After 头：
        # 1) 透传给响应头，供标准客户端读取；
        # 2) 同时放进响应体，让只看 data 的前端也能拿到"等待秒数"做倒计时，
        #    避免用户不知道多久能重试而反复尝试。
        retry_after = exc.headers.get("Retry-After") if exc.headers else None

        return JSONResponse(
            status_code=exc.status_code,
            headers=({"Retry-After": retry_after} if retry_after else None),
            content={
                "code": response_code.code,
                "message": exc.detail,
                "data": {"retry_after": int(retry_after)} if retry_after else None,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """把 Pydantic 的校验错误翻译成用户能看懂的话。

        原先无论什么错误都返回 "Param Error"，用户只知道「哪里不对」，
        不知道「怎么改」——实测注册时密码只有 7 位，界面就只说 Param Error，
        而真正的原因（至少 8 位）藏在 data.detail 里，前端并不展示。

        注意：密码强度在 service 层（validate_password_strength）本就有
        逐条中文提示，但 schema 上的 min_length 会**先**被 Pydantic 拦下，
        于是永远走不到那句更具体的提示。这里补齐翻译，两条路径的措辞
        保持一致。
        """
        errors = exc.errors()
        if not errors:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "code": BusinessCode.PARAM_ERROR.code,
                    "message": "请求参数不正确",
                    "data": None,
                },
            )

        first_err = errors[0]
        loc = [str(x) for x in (first_err.get("loc") or ()) if x != "body"]
        field_name = loc[-1] if loc else ""
        err_type = str(first_err.get("type") or "")
        ctx = first_err.get("ctx") or {}

        # 字段中文名，让提示读起来像人话而不是「password 字段错误」
        FIELD_LABEL = {
            "password": "密码",
            "email": "邮箱",
            "username": "昵称",
            "code": "验证码",
            "refresh_token": "登录凭证",
            "message": "消息内容",
        }
        label = FIELD_LABEL.get(field_name, field_name or "参数")

        # Pydantic 错误类型 → 中文说明。ctx 里带有具体边界值，直接引用。
        if err_type == "value_error":
            if field_name == "email":
                # EmailStr 的报错是英文，且提到 "special-use or reserved name"
                # 这类术语，直接展示等于没说。统一换成中文。
                # 注意它的 ctx 键是 reason（不是 error）—— 实测确认过。
                msg = "邮箱格式不正确"
            else:
                # 自定义 field_validator 抛的 ValueError：消息本就是给人看的
                # 中文原因（如「密码需要包含大写字母」），直接透出，
                # 不要再套一层「xx不正确：...」。
                raw_ctx = ctx.get("error")
                text = str(raw_ctx) if raw_ctx is not None else ""
                if not text:
                    # 退路：从 "Value error, xxx" 里剥出后半段
                    raw_msg = str(first_err.get("msg") or "")
                    text = raw_msg.split(",", 1)[1].strip() if "," in raw_msg else raw_msg
                msg = text or f"{label}不正确"
        elif err_type == "string_too_short":
            limit = ctx.get("min_length")
            msg = f"{label}至少需要 {limit} 个字符" if limit else f"{label}太短"
        elif err_type == "string_too_long":
            limit = ctx.get("max_length")
            msg = f"{label}不能超过 {limit} 个字符" if limit else f"{label}太长"
        elif err_type in ("missing", "value_error_missing"):
            msg = f"缺少{label}"
        elif err_type in ("int_parsing", "float_parsing", "decimal_parsing"):
            msg = f"{label}必须是数字"
        elif err_type == "greater_than_equal":
            msg = f"{label}不能小于 {ctx.get('ge')}"
        elif err_type == "less_than_equal":
            msg = f"{label}不能大于 {ctx.get('le')}"
        elif err_type == "enum":
            msg = f"{label}的取值不在允许范围内"
        else:
            # 未覆盖的类型：给出字段名 + 原始原因，总比笼统一句好
            raw = str(first_err.get("msg") or "").strip()
            msg = f"{label}不正确" + (f"：{raw}" if raw else "")

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "code": BusinessCode.PARAM_ERROR.code,
                "message": msg,
                # 保留结构化信息便于排查；前端只展示 message
                "data": {"field": field_name, "type": err_type,
                         "detail": first_err.get("msg")},
            },
        )


    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        log.exception("Unhandled error: %s", request.url)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": BusinessCode.INTERNAL_ERROR.code,
                "message": "服务器开小差了，请稍后再试",
                "data": str(exc) if getattr(app.state, "debug", False) or getattr(app, "debug", False) else None,
            },
        )