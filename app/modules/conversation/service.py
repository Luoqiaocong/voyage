from typing import Annotated

from fastapi import Depends

from .factory import ConversationFactory


class ConversationService:
    def __init__(
        self, factory: Annotated[ConversationFactory, Depends()]
    ) -> None:
        self.factory = factory

    async def process_message(self, message: str, conversation_id: str):
        async for chunk in self.factory.astream_chat(message, conversation_id):
            yield chunk

    async def get_messages(self, conversation_id: str):
        return await self.factory.get_messages(conversation_id)
