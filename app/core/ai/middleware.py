import json
from collections import Counter
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import AIMessage, ToolMessage

from app.shared.utils import log


def on_tool_error(exc: Exception, request: ToolCallRequest) -> str | None:
    """工具调用最终失败时的友好回退；返回 None 表示不接管，继续抛出原异常。"""
    tool_name = request.tool_call.get("name", "unknown_tool")

    # 失败细节只写日志，不回给用户，避免泄露内部路径/异常等敏感信息
    if isinstance(exc, ValueError):
        log.error(f"[tool] {tool_name} failed: {type(exc).__name__}: {exc}")
        return f"「{tool_name}」暂时不可用，请稍后再试。"

    # 可按需扩展：超时、连接错误等
    if isinstance(exc, (TimeoutError, ConnectionError)):
        log.error(f"[tool] {tool_name} unavailable: {type(exc).__name__}: {exc}")
        return f"「{tool_name}」暂时不可用，请稍后再试。"

    return None


CUSTOM_MIDDLEWARE = [
    # ---------- 输入侧 PII ----------
    # PIIMiddleware(
    #     "phone_number",
    #     detector=(
    #         r"(?:\+?\d{1,3}[\s.-]?)?"
    #         r"(?:\(?\d{2,4}\)?[\s.-]?)?"
    #         r"\d{3,4}[\s.-]?\d{4}"
    #     ),
    #     strategy="mask",
    #     apply_to_input=True,
    # ),
    # PIIMiddleware(
    #     "email",
    #     strategy="redact",
    #     apply_to_input=True,
    #     apply_to_output=False,
    # ),
    # ---------- 上下文压缩：清理过期工具结果 ----------
    # 为什么不选 SummarizationMiddleware：
    #   它每次触发都要额外调用一次 LLM 生成摘要——既是成本也是延迟，
    #   且摘要失败会阻塞对话。本项目的 token 用量按量计费，这笔开销不划算。
    #
    # 选 ContextEditingMiddleware + ClearToolUsesEdit：
    #   纯上下文编辑，不产生任何模型调用，因此不会失败、不会拖慢对话。
    #   对本场景尤其合适——天气/车次/推荐的返回都很长，但过几轮就失去价值，
    #   清掉它们能在不损失关键信息（用户说了什么、模型答了什么）的前提下
    #   把上下文压回可控范围。
    #
    # trigger=8000：supervisor 提示词本身已有约 1100 字符，加上长期记忆与
    #   若干轮工具结果，8000 token 是「开始偏重但远未溢出」的合理起点。
    # keep=3：保留最近 3 条工具结果——模型通常在最近几轮内才需要回看它们。
    ContextEditingMiddleware(
        edits=[
            ClearToolUsesEdit(
                trigger=8000,
                keep=3,
                clear_tool_inputs=True,   # 入参同样占用额度，一并清掉
            )
        ],
    ),
    # ---------- 模型韧性：同模型指数退避重试 ----------
    # 说明：原先的 ModelFallbackMiddleware 已移除——本平台全任务统一使用
    # deepseek-v4.1-flash（OpenCode Go），没有可降级的第二模型；且原降级链指向
    # DashScope 已耗尽额度的模型，实际只会把故障放大。失败交由重试中间件处理。
    ModelRetryMiddleware(
        max_retries=3,
        backoff_factor=2.0,
        initial_delay=1.0,
    ),
    # ---------- 工具调用限流 ----------
    ToolCallLimitMiddleware(
        thread_limit=20,
        run_limit=10,
        # exit_behavior="continue",  # 默认：超限工具被拦截，其它逻辑可继续
    ),
    # ---------- 待办（旅行规划需要时可保留，纯闲聊可去掉）----------
    # TodoListMiddleware(),
    # ---------- 工具：先重试，耗尽后再交给错误处理 ----------
    ToolRetryMiddleware(
        max_retries=3,
        backoff_factor=2.0,
        initial_delay=1.0,
        on_failure="error",
    ),
    ToolErrorMiddleware(on_error=on_tool_error),
    # ---------- 输出侧 PII ----------
    # PIIMiddleware(
    #     "ip",
    #     strategy="redact",
    #     apply_to_input=True,
    #     apply_to_output=True,
    # ),
]


def _tool_signature(tool_call: dict[str, Any]) -> str:
    """把一次工具调用归一成可比对的签名（工具名 + 规整后的参数）。"""
    args = tool_call.get("args") or {}
    try:
        normalized = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        normalized = str(args)
    return f"{tool_call.get('name')}({normalized})"


class DuplicateToolCallMiddleware(AgentMiddleware):
    """打断「同工具、同参数」反复调用的死循环。

    背景（真实事故）：一次「珠海 → 澳门」查票里，澳门没有铁路站，票务
    子 Agent 不收敛，把「珠海周边各站 → 广州/深圳/香港」这一组查询重复了
    274 次（20 组参数、前 7 组各重复 36-38 次）。由于这些调用命中缓存秒回、
    没有任何失败信号，模型不停重调；而 langchain 的 create_agent 默认
    recursion_limit=9999，等于不设上限。单次问答因此烧掉约 1380 万 token。

    这里在每轮模型输出后统计历史里相同签名的调用次数：某签名已出现
    ``max_repeats`` 次后，再出现的同签名调用被判为「无进展」，注入
    ToolMessage 拦截；若本轮全部调用都被拦下，则直接结束本轮子 Agent，
    让模型（或父 Agent）基于已有信息作答，而不是继续空转。

    为什么按「全局累计」而不是「连续重复」计数：事故里的循环是两组参数
    交替出现（A,B,A,B...），只看连续重复会漏判。
    """

    def __init__(self, max_repeats: int = 3) -> None:
        if max_repeats < 1:
            raise ValueError("max_repeats 必须是正整数")
        super().__init__()
        self.max_repeats = max_repeats

    @hook_config(can_jump_to=["end"])
    def after_model(self, state, runtime):  # noqa: ANN001
        messages = state.get("messages", [])
        last_ai = next(
            (
                m
                for m in reversed(messages)
                if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
            ),
            None,
        )
        if last_ai is None:
            return None

        seen: Counter[str] = Counter()
        for message in messages:
            if message is last_ai or not isinstance(message, AIMessage):
                continue
            for tool_call in message.tool_calls or []:
                seen[_tool_signature(tool_call)] += 1

        blocked = [
            tc
            for tc in last_ai.tool_calls
            if seen[_tool_signature(tc)] >= self.max_repeats
        ]
        if not blocked:
            return None

        # 为每个被拦的调用补一条 error ToolMessage：ToolNode 见到同 id 已有结果
        # 便会跳过，从而阻断这些调用，同时不影响本轮其它（未重复的）工具。
        artificial: list[Any] = [
            ToolMessage(
                content=(
                    f"检测到对 {tc.get('name')} 的相同调用已重复 {self.max_repeats} 次，"
                    "已停止重复。请基于已获得的信息作答，不要再用相同参数重试。"
                ),
                tool_call_id=tc["id"],
                name=tc.get("name"),
                status="error",
            )
            for tc in blocked
        ]

        # 本轮所有调用都被判为重复时才结束；否则放行未重复的那些。
        if len(blocked) == len(last_ai.tool_calls):
            artificial.append(
                AIMessage(
                    content="已检测到重复的工具调用并停止，请基于已获得的信息直接回答用户。"
                )
            )
            return {"messages": artificial, "jump_to": "end"}
        return {"messages": artificial}

    async def aafter_model(self, state, runtime):  # noqa: ANN001
        return self.after_model(state, runtime)


#: 子 Agent（ticket / weather / travel）共用的中间件。
#:
#: 为什么主 Agent 的 CUSTOM_MIDDLEWARE 不能直接复用：
#: 主 Agent 关心的是「跨轮次的会话体验」（上下文清理、调用配额），而子 Agent
#: 是「一次性任务」——每次 ainvoke 独立、无 checkpointer，因此这里只保留
#: 真正能防止失控的两项：清理长工具结果、打断重复调用。
#: ToolCallLimitMiddleware 未加在这里：它按 thread 维度计数，子 Agent 没有
#: 持久线程状态，且 langgraph 抛错后 ToolRetryMiddleware 会重跑整条链路，
#: 反而放大开销；重复调用守卫才是针对本次事故的精准拦截。
SUBAGENT_MIDDLEWARE = [
    ContextEditingMiddleware(
        edits=[
            ClearToolUsesEdit(
                trigger=8000,
                keep=3,
                clear_tool_inputs=True,
            )
        ],
    ),
    DuplicateToolCallMiddleware(max_repeats=3),
    ToolErrorMiddleware(on_error=on_tool_error),
]