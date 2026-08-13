from typing import Any

from langchain.messages import AIMessage, HumanMessage

from app.core.ai import AgentFactory


def _thread_config(session_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": session_id}}

async def astream_chat(message: str,session_id:str):
    agent = AgentFactory.get_agent()
    config = _thread_config(session_id)

    stream = agent.astream({"messages": [HumanMessage(content=message)]}, stream_mode="messages",config=config)
    async for event in stream:
        if not (isinstance(event, tuple) and event):
            continue
        chunk = getattr(event[0], "content", None)
        if isinstance(chunk, str) and chunk:
            yield chunk