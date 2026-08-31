from typing import Annotated
from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator
from .auth import get_hashed_id


class UserIdentity(BaseModel):
    id: Annotated[int, Field(description="用户ID")]
    email: Annotated[EmailStr, Field(description="邮箱地址")]

class UserBaseRequest(BaseModel):
    email: Annotated[EmailStr, Field(description="邮箱地址")]
    password: Annotated[str, Field(description="用户密码", min_length=8)] 
    
class UserProfileBase(BaseModel):
    username: Annotated[str | None, Field(description="昵称", max_length=10)] = None
    avatar: Annotated[str | None, Field(description="头像文件名（如 photographer.png）")] = None

class RegisterUserRequest(UserBaseRequest):
    username: Annotated[str, Field(description="用户昵称", min_length=2, max_length=10)]
    code: Annotated[str, Field(description="邮箱验证码", min_length=6, max_length=6)]

    @field_validator("code", mode="before")
    def strip_code(cls, value: str) -> str:
        return value.strip()
    
    model_config = {
                "json_schema_extra": {
                    "examples": [
                        {
                            "email": "admin@example.com",
                            "password": "1234567890",
                            "username": "admin",
                            "code": "123456"
                        }
                    ]
                }
            }
    
class LoginUserRequest(UserBaseRequest):
    
    model_config = {
                "json_schema_extra": {
                    "examples": [
                        {
                            "email": "admin@example.com",
                            "password": "1234567890"
                        }
                    ]
                }
            }

class UserChangePasswordRequest(BaseModel):
    current_password: Annotated[str, Field(description="当前密码", min_length=8)]
    new_password: Annotated[str, Field(description="新密码", min_length=8)]
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "current_password": "1234567890",
                    "new_password": "1234567890abc"
                }
            ]
        }
    }
    
class UserEmailRequest(BaseModel):
    email: Annotated[EmailStr, Field(description="邮箱地址")]
    code: Annotated[str, Field(description="邮箱验证码", min_length=6, max_length=6)]  
    

class UserResetPasswordRequest(BaseModel):
    password: Annotated[str, Field(description="新密码", min_length=8)]
    token: Annotated[str, Field(description="重置密码 临时Token")]



class UserInfo(UserIdentity, UserProfileBase):

    @field_serializer('id')
    def serialize_id(self, id: int):
        return get_hashed_id(id)

    model_config = {"from_attributes": True}
    
class UserProfileUpdate(UserProfileBase):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"username": "new username"},
                {"avatar": "photographer.png"},
                {"username": "new username", "avatar": "photographer.png"},
            ]
        }
    }