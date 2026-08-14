import json
from typing import Annotated, Any

from fastapi import Depends
from .factory import ChatFactory

class ChatService:
    
    def __init__(self,factory:Annotated[ChatFactory, Depends()]) -> None:
        self.factory = factory
        
    async def process_message(self, message: str, session_id: str):
        async for chunk in self.factory.astream_chat(message,session_id):
            yield chunk
            
    async def get_messages(self, session_id: str):
       return  await self.factory.get_messages(session_id)