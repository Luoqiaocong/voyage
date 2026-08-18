from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_serializer

from .auth import get_hashed_id


class UserIdentity(BaseModel):
    id: Annotated[int, Field(description="用户ID")]
    email: Annotated[EmailStr, Field(description="邮箱地址")]

class UserRequest(BaseModel):
    email: Annotated[EmailStr, Field(description="邮箱地址")]
    password: Annotated[str, Field(description="用户密码", min_length=8)] 

class RegisterUserRequest(UserRequest):
    username: Annotated[str, Field(description="用户昵称", min_length=2, max_length=10)]
    
    model_config = {
                "json_schema_extra": {
                    "examples": [
                        {
                            "email": "admin@example.com",
                            "password": "1234567890",
                            "username": "admin"
                        }
                    ]
                }
            }
    
    
class LoginUserRequest(UserRequest):
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



class UserProfileBase(BaseModel):
    username: Annotated[str | None, Field(description="昵称", max_length=10)] = None
    avatar: Annotated[HttpUrl, Field(description="头像链接")]


class UserInfo(UserIdentity, UserProfileBase):

    @field_serializer('id')
    def serialize_id(self, id: int, _info):
        return get_hashed_id(id)

    model_config = {"from_attributes": True}