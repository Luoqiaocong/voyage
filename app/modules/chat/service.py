import json
from typing import Any
from .factory import astream_chat


class ChatService:
    async def process_message(self, message: str, session_id: str):
        async for chunk in astream_chat(message,session_id):
            yield chunk