from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
)

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
    # 说明：本平台全任务统一使用 deepseek-v4.1-flash（OpenCode Go），
    # 没有可降级的第二模型，故不使用 ModelFallbackMiddleware，
    # 失败一律交由重试中间件处理。
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