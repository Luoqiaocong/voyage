from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.shared.utils import get_id



class ConversationResponse(BaseModel):
    conversation_id: str = Field(
        description="对话ID",
        default_factory=get_id,
        pattern=r"^[a-zA-Z0-9]{12}$",
    )
    created_at: datetime = Field(description="创建时间", default_factory=datetime.now)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "123456",
                    "created_at": "2026-09-01T12:34:56.789Z",
                }
            ]
        }
    }


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
