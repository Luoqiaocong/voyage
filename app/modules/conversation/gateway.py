from langchain.messages import HumanMessage, ToolMessage
from langchain_core.messages import AIMessageChunk, convert_to_openai_messages
from langchain_core.runnables import RunnableConfig

from app.core.ai import AgentFactory
from app.core.business import BusinessCode, ConversationException


def _thread_config(conversation_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": conversation_id}}


class ConversationGateway:
    """对话网关：封装与 langgraph Agent 的交互（流式对话、历史读取、线程删除）。"""

    def __init__(self):
        pass

    async def stream_message(self, message: str, conversation_id: str):
        agent = AgentFactory.get_agent()
        config = _thread_config(conversation_id)

        stream = agent.astream(
            {"messages": [HumanMessage(content=message)]},
            stream_mode="messages",
            config=config,
        )
        async for event in stream:
            if not (isinstance(event, tuple) and event):
                continue

            chunk = event[0]

            # 1. 处理工具执行结果 (ToolMessage)
            if isinstance(chunk, ToolMessage):
                yield {
                    "type": "tool_result",
                    "name": getattr(chunk, "name", "tool"),
                    "content": str(chunk.content),
                }
                continue

            # 2. 处理 AI 生成的文本或思考流 (AIMessageChunk)
            if isinstance(chunk, AIMessageChunk):
                # 兼容 DeepSeek / Qwen 的深度思考过程
                reasoning = chunk.additional_kwargs.get("reasoning_content")
                if reasoning:
                    yield {"type": "reasoning", "content": reasoning}

                # 正常回答内容
                if chunk.content and isinstance(chunk.content, str):
                    yield {"type": "text", "content": chunk.content}

    async def get_messages(self, conversation_id: str):
        agent = AgentFactory.get_agent()
        config = _thread_config(conversation_id)

        state = await agent.aget_state(config)
        if not state.values:
            return []
        return convert_to_openai_messages(state.values["messages"])

    async def delete_conversation_thread(self, conversation_id: str):
        checkpointer = AgentFactory.get_checkpointer()
        try:
            await checkpointer.adelete_thread(conversation_id)
            """后续要记录日志为什么删除失败"""
        except Exception as exc:  # 底层删除失败统一映射为业务异常
            raise ConversationException(
                BusinessCode.CONVERSATION_DELETE_FAILED,
                msg=f"删除对话失败",
            ) from exc
