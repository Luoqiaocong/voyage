"""AI 结构化输出：通用骨架（LLM 结构化绑定 + 失败兜底），不依赖任何业务模块。

业务方（如行程模块）传入自己的 Pydantic schema 与可选专属提示词即可复用；
core 层不感知具体结构，消除 core → modules 的反向依赖。
"""
from typing import TypeVar, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.shared.utils import log

from ..llm import TaskKind, get_task_llm

# 结构化输出的模型类型：由调用方传入的 schema 决定（如 ItineraryPlan）
_T = TypeVar("_T", bound=BaseModel)

# 通用系统提示词：未提供专属 instructions 时兜底的约束
_BASE_SYSTEM_PROMPT = (
    "你是一个数据提取助手。请根据用户输入的内容，输出一个符合给定 Schema 的 JSON 对象。必须遵守：\n"
    "1. 结构严格一致：字段名与嵌套层级必须与 Schema 完全一致，禁止新增、重命名或删除字段。\n"
    "2. 类型严格一致：字符串用双引号包裹，数组用 [ ]，对象用 { }，数字用数值（不加引号），布尔用 true/false；\n"
    "   嵌套对象必须以对象形式输出（{...}），绝不能写成带引号的字符串；嵌套数组同理。\n"
    "3. 可空字段：Schema 中可选的字段，输入内容没有或无法确定时就省略该字段，不要填 null、空字符串或编造的取值。\n"
    "4. 取值约束：字段有明确取值限制（如枚举）时，只能从这些取值中选择，禁止自创取值。\n"
    "5. 必填字段：Schema 标记为必填的字段必须给出合理取值，不能缺失。\n"
    "6. 只输出 JSON 对象本身：不要 Markdown 代码块、不要 ```json 标记、不要任何解释性文字或前后缀。"
)


async def extract_structured(
    text: str,
    schema: type[_T],
    *,
    temperature: float = 0.2,
    system_instructions: str | None = None,
) -> _T | None:
    """通用结构化提取：text → 经 schema 校验的 Pydantic 对象；失败返回 None（不打断调用方）。

    - text                : 待提取的原始文本（如对话中的攻略 Markdown）
    - schema              : 任意 Pydantic 模型类，由业务方传入
    - temperature         : 提取用 LLM 温度，默认 0.2（追求稳定）
    - system_instructions : 可选专属系统提示词（如写死完整 JSON 示例增强约束）
    """
    if not text or not text.strip():
        return None

    system_prompt = system_instructions or _BASE_SYSTEM_PROMPT
    structured_llm = get_task_llm(TaskKind.EXTRACT, temperature=temperature).with_structured_output(
        schema, method="json_mode"
    )
    try:
        # ainvoke 的类型签名较宽松（BaseModel | dict），但 with_structured_output
        # 保证输出会经 schema 校验，运行时就是传入 schema 的实例，显式收窄类型。
        return cast(_T, await structured_llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=text),
        ]))
    except Exception as exc:
        # 开发期排查用：打印完整校验信息（含模型原始输出片段）
        log.error(f"[extract_structured] failed: {exc}") 
        return None