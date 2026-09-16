"""AI 结构化输出：优先工具调用，失败回退提示词约束，均不依赖 provider 的 response_format。

为什么这样设计（均由实测决定）：
    OpenCode Go 的 deepseek-v4.1-flash 上三种原生模式的表现——
      json_schema      400 This response_format type is unavailable now
      json_mode        返回合法 JSON 但忽略 schema（字段名由模型自创）
      function_calling 400 Thinking mode does not support this tool_choice
                        —— 除非同时关闭思考模式（reasoning_effort="none"）

    关闭思考后 function_calling 可正常工作，且强制工具调用比提示词约束更可靠
    （结构化数据直接落在 tool_calls.arguments 里，schema 由工具定义承载）。
    因此主路径用工具调用；若通道不支持，则回退到「schema 注入提示词 + 本地校验」，
    该回退只依赖最基础的文本补全，换任何通道都不会退化。

业务方（如行程模块）传入自己的 Pydantic schema 与可选专属提示词即可复用；
core 层不感知具体结构，消除 core → modules 的反向依赖。
"""
import json
from typing import Any, TypeVar, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.shared.utils import log

from ..llm import TaskKind, get_task_llm

# 结构化输出的模型类型：由调用方传入的 schema 决定（如 ItineraryPlan）
_T = TypeVar("_T", bound=BaseModel)

# 通用系统提示词：回退路径使用（工具调用路径由工具定义承载 schema 约束）
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


# ────────────────────── 回退路径：schema 注入提示词 ──────────────────────
def _json_type(field: Any) -> str:
    """尽力推导字段的 JSON 类型名（取不到时给宽松描述，交给模型自行判断）。"""
    annotation = getattr(field, "annotation", None)
    if annotation is None:
        return "any"

    origin = getattr(annotation, "__origin__", None)
    if origin in (list, set, tuple):
        return "array"
    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return "object"
        if issubclass(annotation, bool):
            return "boolean"
        if issubclass(annotation, int):
            return "integer"
        if issubclass(annotation, float):
            return "number"
        if issubclass(annotation, str):
            return "string"
    # Optional[...] / Union[...] / Literal[...] 等，用注解文本兜底
    return str(annotation).replace("typing.", "")


def _nested_model(field: Any) -> type[BaseModel] | None:
    """取字段的嵌套 Pydantic 模型（支持直接嵌套与 list[...] 元素）。"""
    annotation = getattr(field, "annotation", None)
    candidates = [annotation]
    candidates.extend(getattr(annotation, "__args__", ()) or ())
    for candidate in candidates:
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def _render_schema(schema: type[BaseModel], indent: str = "") -> str:
    """把 Pydantic 模型渲染成模型可读的字段契约（递归展开嵌套模型）。"""
    lines: list[str] = []
    for index, (name, field) in enumerate(schema.model_fields.items(), start=1):
        flag = "必填" if field.is_required() else "可选"
        desc = f" — {field.description}" if field.description else ""
        lines.append(f'{indent}  {index}. "{name}": {_json_type(field)}（{flag}）{desc}')

        # 嵌套模型继续展开，否则模型会把子字段和父字段混在同一层
        inner = _nested_model(field)
        if inner is not None:
            lines.append(_render_schema(inner, indent + "     "))
    return "\n".join(lines) if lines else f"{indent}  （无字段）"


def _build_skeleton(schema: type[BaseModel]) -> str:
    """构造带类型的结构骨架，明确展示嵌套层级（用 null 占位而非编造取值）。"""
    skeleton: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        inner = _nested_model(field)
        annotation = getattr(field, "annotation", None)
        origin = getattr(annotation, "__origin__", None)

        if inner is not None:
            value: Any = json.loads(_build_skeleton(inner))
            skeleton[name] = [value] if origin in (list, set, tuple) else value
        else:
            skeleton[name] = None
    return json.dumps(skeleton, ensure_ascii=False, indent=2)


def _build_system_prompt(schema: type[BaseModel], instructions: str | None) -> str:
    """组装回退路径的系统提示词：基础约束 + 字段契约 + 结构骨架。"""
    base = instructions or _BASE_SYSTEM_PROMPT
    return (
        f"{base}\n\n"
        f"# 本次要求的 Schema：{schema.__name__}\n"
        f"字段契约（必须严格遵守，不得增删或改名）：\n{_render_schema(schema)}\n\n"
        f"# 结构骨架（仅示意字段名与嵌套层级，null 处需按实际内容填写）\n{_build_skeleton(schema)}"
    )


def _parse_json_object(raw: str) -> Any:
    """从模型输出里抠出 JSON 对象：容忍 ``` 代码块与前后解释性文字。"""
    text = raw.strip()

    # 1. 优先剥掉 Markdown 代码块围栏
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()

    # 2. 直接尝试解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. 退一步：截取第一个 { 到最后一个 } 之间的内容
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"模型输出中未找到 JSON 对象：{raw[:200]!r}")


# ────────────────────── 抽取实现 ──────────────────────
async def _extract_via_tool_call(
    text: str,
    schema: type[_T],
    temperature: float,
    instructions: str | None,
) -> _T:
    """主路径：强制模型调用一个参数即 schema 的工具，直接取回结构化参数。

    说明：EXTRACT 任务已在 get_task_llm 中关闭思考模式（reasoning_effort="none"），
    否则上游会拒绝强制 tool_choice。
    """
    llm = get_task_llm(TaskKind.EXTRACT, temperature=temperature)
    structured = llm.with_structured_output(schema, method="function_calling")
    prompt = instructions or "请把用户提供的内容提取为结构化数据。"
    result = await structured.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=text),
    ])
    if not isinstance(result, schema):
        raise ValidationError.from_exception_data(
            schema.__name__,
            [{"type": "value_error", "loc": (), "input": result,
              "ctx": {"error": ValueError(f"工具调用返回类型异常: {type(result).__name__}")}}],
        )
    return cast(_T, result)


async def _extract_via_prompt(
    text: str,
    schema: type[_T],
    temperature: float,
    instructions: str | None,
) -> _T:
    """回退路径：schema 注入提示词 + 本地 Pydantic 校验（不依赖任何原生结构化能力）。"""
    llm = get_task_llm(TaskKind.EXTRACT, temperature=temperature)
    response = await llm.ainvoke([
        SystemMessage(content=_build_system_prompt(schema, instructions)),
        HumanMessage(content=text),
    ])
    raw = response.content if isinstance(response.content, str) else str(response.content)
    payload = _parse_json_object(raw)
    return cast(_T, TypeAdapter(schema).validate_python(payload))


async def extract_structured(
    text: str,
    schema: type[_T],
    *,
    temperature: float = 0.2,
    system_instructions: str | None = None,
    max_attempts: int = 2,
) -> _T | None:
    """通用结构化提取：text → 经 schema 校验的 Pydantic 对象；失败返回 None（不打断调用方）。

    策略：先走工具调用；通道不支持时回退提示词路径；两者都失败才返回 None。

    - text                : 待提取的原始文本（如对话中的攻略 Markdown）
    - schema              : 任意 Pydantic 模型类，由业务方传入
    - temperature         : 提取用 LLM 温度，默认 0.2（追求稳定）
    - system_instructions : 可选专属系统提示词（回退路径使用）
    - max_attempts        : 回退路径的尝试次数（含首次），默认 2
    """
    if not text or not text.strip():
        return None

    # ---------- 主路径：工具调用 ----------
    try:
        return await _extract_via_tool_call(text, schema, temperature, system_instructions)
    except ValidationError as exc:
        log.error(f"[extract_structured] 工具调用结果校验失败: {_brief(exc)}")
    except Exception as exc:  # noqa: BLE001
        # 通道不支持工具调用（如 400）或网络异常：记录后转回退路径
        log.error(f"[extract_structured] 工具调用不可用，转回退路径: {type(exc).__name__}: {_brief(exc)}")

    # ---------- 回退路径：提示词 + 本地校验（含一次纠错重试） ----------
    return await _extract_with_retry(
        text, schema, temperature, system_instructions, max_attempts
    )


async def _extract_with_retry(
    text: str,
    schema: type[_T],
    temperature: float,
    instructions: str | None,
    max_attempts: int,
) -> _T | None:
    """回退路径实现：首次输出不符则把校验错误回灌给模型纠错重试。"""
    llm = get_task_llm(TaskKind.EXTRACT, temperature=temperature)
    system_prompt = _build_system_prompt(schema, instructions)
    messages: list = [SystemMessage(content=system_prompt), HumanMessage(content=text)]

    last_error: Exception | None = None
    raw = ""
    for attempt in range(1, max_attempts + 1):
        try:
            response = await llm.ainvoke(messages)
            raw = response.content if isinstance(response.content, str) else str(response.content)
            payload = _parse_json_object(raw)
            return cast(_T, TypeAdapter(schema).validate_python(payload))
        except ValidationError as exc:
            last_error = exc
            log.error(f"[extract_structured] 第 {attempt} 次校验失败: {_brief(exc)}")
            if attempt >= max_attempts:
                break
            # 把校验错误回灌，让模型针对性纠正（比重新问一遍有效得多）
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=text),
                AIMessage(content=raw),
                HumanMessage(
                    content=(
                        "上面的输出不符合 Schema，校验错误如下，请修正后重新只输出完整 JSON：\n"
                        f"{_brief(exc, limit=800)}"
                    )
                ),
            ]
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            log.error(f"[extract_structured] 第 {attempt} 次解析失败: {type(exc).__name__}: {exc}")
            if attempt >= max_attempts:
                break
        except Exception as exc:  # noqa: BLE001
            # 通道异常（网络/鉴权）：重试无意义，直接返回
            log.error(f"[extract_structured] 调用失败: {type(exc).__name__}: {exc}")
            return None

    log.error(f"[extract_structured] 已放弃（共 {max_attempts} 次），最后错误: {last_error}")
    return None


def _brief(exc: Exception, limit: int = 500) -> str:
    """把校验错误压成简短文本，便于回灌给模型。"""
    text = str(exc).replace("\n", " ")
    return text[:limit]
