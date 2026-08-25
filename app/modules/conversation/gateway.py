import asyncio

from langchain.messages import HumanMessage, ToolMessage
from langchain_core.messages import AIMessageChunk, convert_to_openai_messages
from langchain_core.runnables import RunnableConfig

from app.core.ai import AgentFactory
from app.core.business import BusinessCode, ConversationException


def _thread_config(conversation_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": conversation_id}}


class ConversationGateway:
    """对话网关：封装与 langgraph Agent 的交互（流式对话、历史读取、线程删除）。"""

    # -------------------- 1. 查询历史消息 --------------------
    async def get_messages(self, conversation_id: str):
        agent = AgentFactory.get_agent()
        config = _thread_config(conversation_id)

        state = await agent.aget_state(config)
        if not state.values:
            return []
        return convert_to_openai_messages(state.values["messages"])

    async def get_last_ai_text(self, conversation_id: str) -> str:
        """取最后一条含文本内容的 AI 回复；没有则返回空串（供行程提取等场景复用）。"""
        messages = await self.get_messages(conversation_id)
        for message in reversed(messages):
            if message.get("role") != "assistant":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
        return ""

    # -------------------- 2. 流式发送消息 --------------------
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

    # -------------------- 3. 删除会话 --------------------
    async def delete_conversation(self, conversation_id: str):
        checkpointer = AgentFactory.get_checkpointer()
        try:
            await checkpointer.adelete_thread(conversation_id)
        except Exception as exc:
            raise ConversationException(
                BusinessCode.CONVERSATION_DELETED_FAILED,
            ) from exc  # 保留原始异常信息，方便调试

    async def delete_conversation_batch(
        self,
        conversation_ids: list[str],
    ) -> None:
        if not conversation_ids:
            return
        tasks = [self.delete_conversation(conv_id) for conv_id in conversation_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # TODO(日志): 引入日志设施后，遍历 results 记录删除失败的会话
