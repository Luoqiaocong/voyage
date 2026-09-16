from langchain.agents.middleware import (
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
    # ---------- 上下文压缩 ----------
    # 启用时需按当前通道取模型：from .llm import get_task_llm, TaskKind
    # SummarizationMiddleware(
    #     model=get_task_llm(TaskKind.EXTRACT),
    #     trigger=("tokens", 4000),
    #     keep=("messages", 20),
    # ),
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