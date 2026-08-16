from typing import Annotated

from fastapi import Depends

from .gateway import ConversationGateway


class ConversationService:
    def __init__(
        self, gateway: Annotated[ConversationGateway, Depends()]
    ) -> None:
        self.gateway = gateway

    async def send_message(self, message: str, conversation_id: str):
        async for chunk in self.gateway.stream_message(message, conversation_id):
            yield chunk

    async def get_messages(self, conversation_id: str, **kwargs):
        return await self.gateway.get_messages(conversation_id, **kwargs)

    async def delete_conversation(self, conversation_id: str):
        return await self.gateway.delete_conversation_thread(conversation_id)
