from langchain.agents.middleware import (
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
)

from app.shared.utils import log

from .llm import VoyageModel, get_llm


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
    # ---------- 上下文压缩 ----------
    # SummarizationMiddleware(
    #     model=get_llm(model=VoyageModel.DASHCOPE_QWEN_PLUS_1220),
    #     trigger=("tokens", 4000),
    #     keep=("messages", 20),
    # ),
    # ---------- 模型韧性：先同模型重试，再降级 ----------
    ModelRetryMiddleware(
        max_retries=3,
        backoff_factor=2.0,
        initial_delay=1.0,
    ),
    ModelFallbackMiddleware(
        get_llm(model=VoyageModel.DASHCOPE_QWEN_3_7_PLUS_2026_05_26),
        get_llm(model=VoyageModel.DASHCOPE_QWEN_3_6_FLASH_2026_04_16),
        get_llm(model=VoyageModel.DASHCOPE_GLM_5),
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