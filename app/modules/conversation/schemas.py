from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.shared.utils import to_local_display


class ConversationResponse(BaseModel):
    """会话响应"""
    id: str = Field(description="会话ID", pattern=r"^[a-zA-Z0-9]{12}$")
    title: str | None = Field(description="会话标题")
    created_at: datetime = Field(description="创建时间（UTC）")

    # 返回时统一转为上海时区展示
    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime) -> str:
        return to_local_display(dt)

    model_config = {"from_attributes": True}


class ConversationMessageRequest(BaseModel):
    message: Annotated[
        str,
        Field(description="对话消息", min_length=1, max_length=2048),
    ]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "how are you today?",
                }
            ]
        }
    }


class ConversationTitleRequest(BaseModel):
    title: Annotated[
        str,
        Field(description="会话标题", min_length=1, max_length=64),
    ]

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("会话标题不能为空")
        return v


class UserConversationsResponse(BaseModel):
    conversations: list[ConversationResponse]
