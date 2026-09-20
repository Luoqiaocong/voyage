from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator

from .auth import get_hashed_id, password_weak_reason


class UserIdentity(BaseModel):
    id: Annotated[int, Field(description="用户ID")]
    email: Annotated[EmailStr, Field(description="邮箱地址")]

class UserBaseRequest(BaseModel):
    """登录/注册共用的请求基类。

    密码这里**不写 min_length**，改为调用 password_weak_reason：
      · 写了 min_length 只能表达「长度不够」，而实际规则还有大小写与数字；
        长度够但缺大写时，Pydantic 放行，错误要等到 service 层才报，
        两条路径的提示不一致。
      · 更要紧的是：Pydantic 的报错会先被 422 处理器接管，
        而那个处理器原先一律返回 "Param Error"，用户完全不知道该怎么改。
      · 现在这里统一走同一条规则函数，异常消息即具体原因
        （「密码长度至少 8 位」/「密码需要包含大写字母」），
        前端直接展示 message 即可。
    """
    email: Annotated[EmailStr, Field(description="邮箱地址")]
    password: Annotated[str, Field(description="用户密码：至少 8 位，含大小写字母与数字")]

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        reason = password_weak_reason(v)
        if reason:
            # ValueError 的消息会被 Pydantic 放进 errors()[0]["msg"]，
            # 但不是我们想要的展示文案；真正的文案由 422 处理器按
            # value_error 分支给出。这里只负责「拦住」。
            raise ValueError(reason)
        return v

class UserProfileBase(BaseModel):
    """昵称/头像的**共用字段定义**，刻意不带长度约束。

    为什么不能在这里写 max_length：
      它同时被 UserInfo（**响应**模型）与 UserProfileUpdate（输入模型）继承。
      响应模型上用 Field(max_length=10) 会变成**读取时的校验** ——
      只要库里有一个超过 10 字的昵称（历史数据、后台导入、脚本写入都可能），
      该用户的 GET /users/info 就会 500，而前端登录后第一件事就是调它，
      等于账号直接不可用。实测已复现：昵称 'probe-admin'（11 字）触发
      ValidationError，接口返回 500 而非降级展示。

      长度约束应当只加在**输入**模型上（RegisterUserRequest 与
      UserProfileUpdate 各自声明），读取路径一律宽松。
    """
    username: Annotated[str | None, Field(description="昵称")] = None
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
    
class UserResetPasswordRequest(BaseModel):
    password: Annotated[str, Field(description="新密码", min_length=8)]
    token: Annotated[str, Field(description="重置密码 临时Token")]


class UserDeleteAccountRequest(BaseModel):
    """注销账号：用邮箱验证码二次确认。

    为什么用验证码而不是密码：
      · 注销不可逆，必须有一道「证明你是本人」的关口；
      · 但让用户在这里再输一次密码，等于在一张弹窗里收集密码 ——
        视觉上更像钓鱼表单，且与「修改密码」的语义混淆；
      · 验证码发到账号绑定的邮箱（由后端从当前登录用户取，前端不必填），
        既证明了对邮箱的控制权，又不必在注销路径上传输密码。

    只收 code 一个字段：邮箱从鉴权态推导，避免前端传任意邮箱导致
    「给别人的邮箱发码」这类越权可能。
    """

    code: Annotated[str, Field(description="邮箱验证码（6 位）", min_length=6, max_length=6)]

    @field_validator("code", mode="before")
    def strip_code(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    model_config = {
        "json_schema_extra": {"examples": [{"code": "123456"}]}
    }



class UserInfo(UserIdentity, UserProfileBase):
    # 只读回显：前端据此决定是否展示管理端入口。
    # 注意这里只「读」——写入路径被 SELF_EDITABLE_FIELDS 白名单挡住，
    # 用户无法通过 PATCH /users/info 修改这两个字段。
    role: Annotated[str, Field(description="角色：user / admin / super_admin")] = "user"
    is_active: Annotated[bool, Field(description="账号是否启用")] = True

    @field_serializer('id')
    def serialize_id(self, id: int):
        return get_hashed_id(id)

    model_config = {"from_attributes": True}
    
class UserProfileUpdate(UserProfileBase):
    """用户自助修改资料。

    长度约束必须声明在这里（而不是共用的 UserProfileBase），
    否则会变成响应模型的读取校验，详见 UserProfileBase 的说明。
    """
    username: Annotated[
        str | None,
        Field(description="昵称", min_length=2, max_length=10),
    ] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"username": "newname"},
                {"avatar": "photographer.png"},
                {"username": "newname", "avatar": "photographer.png"},
            ]
        }
    }
    
class UserRefreshTokenRequest(BaseModel):
    refresh_token: Annotated[str, Field(description="Refresh Token", min_length=32, max_length=128)]