from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


class VerifyEmailRequest(BaseModel):
    """发送验证码请求。"""

    email: Annotated[EmailStr, Field(description="邮箱地址")]


class EmailCodeRequest(BaseModel):
    """邮箱 + 验证码请求（用于验证码换重置令牌）。"""

    email: Annotated[EmailStr, Field(description="邮箱地址")]
    code: Annotated[str, Field(description="邮箱验证码", min_length=6, max_length=6)]
    
    
class AccessTokenRequest(BaseModel):
    refresh_token: Annotated[str, Field(description="Refresh Token", min_length=32, max_length=128)]