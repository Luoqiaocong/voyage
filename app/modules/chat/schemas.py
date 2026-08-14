from datetime import datetime
import time

from pydantic import BaseModel
from app.shared.utils import get_id
from pydantic import Field
from typing import Annotated

class SessionBase(BaseModel):
    session_id: Annotated[str,Field(description="会话id",pattern=r"^sess_[a-zA-Z0-9]+$")]

class SessionRequest(SessionBase):
    pass

class SessionResponse(BaseModel):
    session_id: str = Field(description="会话ID", default_factory=get_id)
    created_at: datetime = Field(description="创建时间", default_factory=datetime.now)

class ChatRequest(SessionBase):
    message: Annotated[str,Field(description="对话消息",min_length=1,max_length=2048)]
    session_id: Annotated[str,Field(description="会话id",pattern=r"^sess_[a-zA-Z0-9]+$")]
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "how are you today?",
                    "session_id": "sess_123456"
                }
            ]
        }
    }

