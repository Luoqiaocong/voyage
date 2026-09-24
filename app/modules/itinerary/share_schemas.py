"""行程分享的请求/响应模型。"""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.shared.utils import to_local_display


class CreateShareRequest(BaseModel):
    """创建分享链接。"""

    allow_copy: Annotated[
        bool, Field(description="是否允许访问者复制行程到自己的账号（默认是）")
    ] = True
    allow_edit: Annotated[
        bool, Field(description="是否允许访问者直接编辑该行程（默认否；需谨慎开启）")
    ] = False
    password: Annotated[
        str | None,
        Field(default=None, min_length=4, max_length=32, description="访问密码，留空表示无需密码"),
    ] = None
    expires_in_days: Annotated[
        int | None,
        Field(default=None, ge=1, le=365, description="有效天数；留空表示永不过期"),
    ] = None

    @field_validator("password", mode="before")
    @classmethod
    def blank_password_to_none(cls, value: object) -> object:
        """把纯空白密码视作「不设密码」，避免出现空字符串密码这种歧义状态。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ShareItem(BaseModel):
    """分享链接详情（仅分享者可见）。

    不回传密码：明文不落库，只回 has_password 让前端知道是否设了密码。
    """

    id: Annotated[int, Field(description="分享 ID")]
    itinerary_id: Annotated[int, Field(description="行程 ID")]
    token: Annotated[str, Field(description="分享令牌")]
    url: Annotated[str, Field(description="完整分享链接")]
    allow_copy: Annotated[bool, Field(description="是否允许复制")]
    allow_edit: Annotated[bool, Field(description="是否允许编辑")]
    has_password: Annotated[bool, Field(description="是否设置了访问密码")]
    expires_at: Annotated[datetime | None, Field(description="过期时间（UTC）")] = None
    revoked_at: Annotated[datetime | None, Field(description="撤销时间（UTC）")] = None
    view_count: Annotated[int, Field(description="访问次数")]
    created_at: Annotated[datetime, Field(description="创建时间（UTC）")]
    status: Annotated[str, Field(description="状态：active / expired / revoked")]

    @field_serializer("expires_at", "revoked_at", "created_at")
    def serialize_dt(self, value: datetime | None) -> str | None:
        return to_local_display(value) if value else None


class ShareListResponse(BaseModel):
    """某行程的全部分享链接。"""

    shares: list[ShareItem]


class ShareCheckResponse(BaseModel):
    """访问分享链接的「预检」结果：是否需要密码、是否可用。"""

    available: Annotated[bool, Field(description="链接当前是否可用（未过期/未撤销）")]
    requires_password: Annotated[bool, Field(description="是否需要输入密码")]
    reason: Annotated[str | None, Field(description="不可用时的原因说明")] = None
    destination: Annotated[str | None, Field(description="目的地（便于未登录时展示）")] = None
    days: Annotated[int | None, Field(description="行程天数")] = None


class SharedItineraryResponse(BaseModel):
    """通过分享链接访问到的行程内容。"""

    itinerary_id: Annotated[int, Field(description="行程 ID")]
    plan: Annotated[dict, Field(description="行程计划")]
    allow_copy: Annotated[bool, Field(description="是否允许复制")]
    allow_edit: Annotated[bool, Field(description="是否允许编辑")]
    view_count: Annotated[int, Field(description="本次访问后的累计访问次数")]
    owner_name: Annotated[str | None, Field(description="分享者昵称")] = None
    created_at: Annotated[datetime, Field(description="行程创建时间（UTC）")]
    updated_at: Annotated[datetime, Field(description="行程更新时间（UTC）")]

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, value: datetime) -> str:
        return to_local_display(value)


class CopySharedRequest(BaseModel):
    """把分享的行程复制到自己的账号。"""

    title_suffix: Annotated[
        str | None, Field(default=None, max_length=20, description="可选：复制后的备注后缀")
    ] = None


class ExtendSharedRequest(BaseModel):
    """访问者在分享链接上做编辑（仅在 allow_edit=true 时可用）。

    只接受独立字段（预算/偏好/交通/提醒/住宿），与行程模块的 PATCH 白名单一致；
    每日安排等派生内容不允许通过分享链接改，避免破坏 days 与 daily_plans 的一致性。
    """

    budget: Annotated[int | None, Field(default=None, ge=0, description="总预算（元）")] = None
    preferences: Annotated[list[str] | None, Field(default=None, description="旅行偏好标签")] = None
    transport: Annotated[str | None, Field(default=None, description="往返交通建议")] = None
    tips: Annotated[list[str] | None, Field(default=None, description="出行提醒")] = None

    model_config = {"extra": "forbid"}


class ExtendSharedResponse(BaseModel):
    """编辑请求的返回：是否已落库 + 合并后的行程内容。

    若访问者不是行程所有者，改动不会被写入原件（避免多人同时改同一份行程
    互相覆盖），而是返回合并结果供前端自行保存；is_applied 明确告知这一点。
    """

    is_applied: Annotated[bool, Field(description="改动是否已写入原行程")]
    plan: Annotated[dict, Field(description="合并后的行程计划")]
