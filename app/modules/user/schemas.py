from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


class UserRequest(BaseModel):
    email: Annotated[EmailStr, Field(description="邮箱地址")]
    password: Annotated[str, Field(description="密码", min_length=8)]


class RegisterUserRequest(UserRequest):
    username: Annotated[str, Field(description="昵称", min_length=2, max_length=10)]
    
class LoginUserRequest(UserRequest):
    pass
