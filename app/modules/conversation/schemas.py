from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_serializer

from .util import get_id


class ConversationResponse(BaseModel):
    """会话响应"""
    id: str = Field(description="会话ID", pattern=r"^[a-zA-Z0-9]{12}$")
    title: str | None = Field(description="会话标题")
    created_at: datetime = Field(description="创建时间（UTC）")
    
    # ✅ 返回时格式化时间（可选）
    @field_serializer('created_at')
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
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

class UserConversationsResponse(BaseModel):
    conversations: list[ConversationResponse]
