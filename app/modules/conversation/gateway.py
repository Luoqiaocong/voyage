import asyncio
from typing import Annotated

from fastapi import Depends
from langchain.messages import HumanMessage, ToolMessage
from langchain_core.messages import AIMessageChunk, convert_to_openai_messages
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai import AgentFactory
from app.core.ai.opencode import use_session
from app.core.business import BusinessCode, ConversationException
from app.shared.db import get_db
from app.shared.db.models import Conversation
from app.shared.utils import log


def _thread_config(conversation_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": conversation_id}}


class ConversationGateway:
    """对话网关：封装与 langgraph Agent 的交互（流式对话、历史读取、线程删除）。"""

    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
        # 需要 session 来加载当前会话所属用户的长期记忆（注入 system prompt）
        self.db = db

    async def _apply_memory(self, conversation_id: str) -> None:
        """把该会话所属用户的长期记忆装载到 AgentFactory。

        失败不阻断对话：记忆属于增强项，缺失时应降级为「没有记忆」而不是报错。
        """
        from app.modules.memory.repo import MemoryRepo
        from app.modules.memory.service import MemoryService

        try:
            user_id = (
                await self.db.execute(
                    select(Conversation.user_id).where(Conversation.id == conversation_id)
                )
            ).scalar_one_or_none()
            if user_id is None:
                return
            service = MemoryService(repo=MemoryRepo(db=self.db), db=self.db)
            AgentFactory.apply_memory(await service.build_memory_context(user_id))
        except Exception:
            log.exception("[memory] 加载记忆上下文失败，本次对话按无记忆处理")

    # -------------------- 1. 查询历史消息 --------------------
    async def get_messages(self, conversation_id: str):
        agent = AgentFactory.get_agent()
        config = _thread_config(conversation_id)

        state = await agent.aget_state(config)
        if not state.values:
            return []
        return convert_to_openai_messages(state.values["messages"])

    async def get_messages_page(
        self, conversation_id: str, *, limit: int | None = None
    ) -> dict:
        """分页返回历史消息，并收敛字段。

        两个问题一起解决：

        1. **体积**：原先一次性返回全部消息，长对话会返回巨大的响应体。
           这里按「轮次」截断——一轮 = 一条 user 消息及其后的所有 assistant/tool
           消息。按轮截断而不是按条截断，避免出现「有回答没提问」的断裂。

        2. **泄露与噪音**：convert_to_openai_messages 会把工具调用的入参
           （tool_calls[].function.arguments）原样带出。这些内容是模型内部调度
           细节，对前端渲染无用，且可能包含用户隐私的中间摘要。这里剥掉入参，
           只保留工具名，让前端仍能画出「调用了什么工具」的时间线。

        Returns:
            {"messages": [...], "total_rounds": int, "returned_rounds": int,
             "truncated": bool}
        """
        raw = await self.get_messages(conversation_id)
        if not raw:
            return {"messages": [], "total_rounds": 0, "returned_rounds": 0, "truncated": False}

        # 按 user 消息切分轮次
        rounds: list[list[dict]] = []
        for message in raw:
            if message.get("role") == "user" or not rounds:
                rounds.append([message])
            else:
                rounds[-1].append(message)

        total_rounds = len(rounds)
        # limit 为空或非正数时返回全部轮次
        selected = rounds[-limit:] if (limit and limit > 0) else rounds

        messages = [self._sanitize(m) for group in selected for m in group]
        return {
            "messages": messages,
            "total_rounds": total_rounds,
            "returned_rounds": len(selected),
            "truncated": len(selected) < total_rounds,
        }

    @staticmethod
    def _sanitize(message: dict) -> dict:
        """收敛单条消息的返回字段。

        assistant 的 tool_calls 只保留工具名，去掉 arguments（见方法说明）。
        content 若是多模态数组则原样返回，交由前端处理。
        """
        cleaned = {k: v for k, v in message.items() if k != "tool_calls"}
        tool_calls = message.get("tool_calls")
        if tool_calls:
            cleaned["tool_calls"] = [
                {"name": (call.get("function") or {}).get("name", "unknown")}
                for call in tool_calls
                if isinstance(call, dict)
            ]
        return cleaned

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
        """流式发送消息。

        OpenCode Go 要求每个请求携带 x-opencode-session 头（缺失直接 400），
        头值在 httpx 发出请求时从上下文读取，故整个流式过程必须包在会话上下文内。
        """
        # 注入长期记忆后再取 agent：apply_memory 可能重建 agent 实例
        await self._apply_memory(conversation_id)
        agent = AgentFactory.get_agent()
        config = _thread_config(conversation_id)

        from app.shared.observability import record_chat
        import time

        started = time.perf_counter()
        ok = True
        try:
            with use_session(conversation_id):
                stream = agent.astream(
                    {"messages": [HumanMessage(content=message)]},
                    stream_mode="messages",
                    config=config,
                )
                async for event in self._translate(stream):
                    yield event
        except Exception:
            # 失败也要记一次，否则错误率统计不到（异常继续向上抛给 service 处理）
            ok = False
            raise
        finally:
            # 流式生成器的 finally 在客户端断开时同样会执行，
            # 因此这条延迟记录覆盖「正常结束」与「中途断开」两种情况。
            await record_chat(ok=ok, ms=(time.perf_counter() - started) * 1000)

    @staticmethod
    async def _translate(stream):
        """把 langgraph 的原始事件流翻译成前端可消费的 SSE 事件。"""
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

            # 2. 处理 AI 生成的文本、工具调用与思考流 (AIMessageChunk)
            if isinstance(chunk, AIMessageChunk):
                # 模型决定调用工具：先推 tool_call，前端可立即展示“正在调用”
                for tool_call in chunk.tool_call_chunks or []:
                    name = tool_call.get("name")
                    if name:
                        yield {"type": "tool_call", "name": name}

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
    ) -> list[BaseException | None]:
        """批量清理 langgraph checkpoint；返回每个会话的清理结果，异常对象表示失败（由调用方降级记录）。"""
        if not conversation_ids:
            return []
        tasks = [self.delete_conversation(conv_id) for conv_id in conversation_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True) # ✅ 与传入顺序一致（无论完成先后）,如果按完成顺序排序则使用as_completed
        return list(results)
