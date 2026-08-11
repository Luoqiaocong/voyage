from app.core.supervisor import supervisor_agent


class ChatService:
    async def process_message(self, message: str, session_id: str | None = None) -> tuple[str, str]:
        # TODO: use supervisor_agent with proper streaming
        return f"Echo: {message}", session_id or "new-session"


chat_service = ChatService()