from pydantic import BaseModel
from app.shared.utils.generate_uid_sessid import get_id
from pydantic import Field
from typing import Annotated

class ChatRequest(BaseModel):
    message: Annotated[str,Field(description="对话消息")]
    session_id: Annotated[str,Field(description="会话id",default_factory=get_id)]
    
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

