import json

from fastapi import Depends
from langchain_core.messages import convert_to_openai_messages
from langchain.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from app.core.ai import AgentFactory

def _thread_config(session_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": session_id}}

class ChatFactory:
    def __init__(self):
        pass
               
    async def astream_chat(self,message: str,session_id:str):
        agent = AgentFactory.get_agent()
        config = _thread_config(session_id)

        stream = agent.astream({"messages": [HumanMessage(content=message)]}, stream_mode="messages",config=config)
        async for event in stream:
            if not (isinstance(event, tuple) and event):
                continue
            chunk = getattr(event[0], "content", None)
            if isinstance(chunk, str) and chunk:
                yield chunk
                
    async def get_messages(self,session_id:str):
        agent = AgentFactory.get_agent()
        config = _thread_config(session_id)
        
        state = await agent.aget_state(config)
        # print(type(state.values))  # 这里应有 messages 等
        # json_output = json.dumps(
        # {"messages": [m.model_dump() for m in state.values["messages"]]},
        # ensure_ascii=False,
        # indent=2
        # )
        # print(json_output)
        return convert_to_openai_messages(state.values["messages"])