"""AI 结构化输出：通用骨架（LLM 结构化绑定 + 失败兜底），不依赖任何业务模块。

业务方（如行程模块）传入自己的 Pydantic schema 与可选专属提示词即可复用；
core 层不感知具体结构，消除 core → modules 的反向依赖。
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.ai.llm import get_llm

# 通用系统提示词：未提供专属 instructions 时兜底的约束
_BASE_SYSTEM_PROMPT = (
    "你是一个数据提取助手：把用户提供的内容整理为 JSON，"
    "字段必须严格符合给定结构，禁止新增、改名或删除字段。"
    "只输出 JSON，不要输出任何其他文字或 Markdown 代码块。"
)


async def extract_structured(
    text: str,
    schema: type,
    *,
    temperature: float = 0.2,
    system_instructions: str | None = None,
):
    """通用结构化提取：text → 经 schema 校验的 Pydantic 对象；失败返回 None（不打断调用方）。

    - text                : 待提取的原始文本（如对话中的攻略 Markdown）
    - schema              : 任意 Pydantic 模型类，由业务方传入
    - temperature         : 提取用 LLM 温度，默认 0.2（追求稳定）
    - system_instructions : 可选专属系统提示词（如写死完整 JSON 示例增强约束）
    """
    if not text or not text.strip():
        return None

    system_prompt = system_instructions or _BASE_SYSTEM_PROMPT
    structured_llm = get_llm(temperature=temperature).with_structured_output(
        schema, method="function_calling"
    )
    try:
        return await structured_llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=text),
        ])
    except Exception as exc:
        # 开发期排查用：打印完整校验信息（含模型原始输出片段）
        print(f"[extract_structured] failed: {exc}")  # noqa: T201
        return None