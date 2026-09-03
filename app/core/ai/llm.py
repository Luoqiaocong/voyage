from enum import StrEnum
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import config


class VoyageModel(StrEnum):
    """Voyage 平台支持的模型枚举"""
    DEEPSEEK_V4_FLASH = "deepseek-v4-flash"
    DEEPSEEK_V4_PRO = "deepseek-v4-pro"
    QWEN_MAX = "qwen-max"
    DASHCOPE_GLM_5 = "glm-5"
    DASHCOPE_QWEN_PLUS_1220 = "qwen-plus-1220"
    DASHCOPE_QWEN_3_7_PLUS_2026_05_26 = "qwen3.7-plus-2026-05-26"
    DASHCOPE_QWEN_3_6_FLASH_2026_04_16="qwen3.6-flash-2026-04-16"


class TaskKind(StrEnum):
    """LLM 任务类型：决定默认模型与温度（调用处仍可覆盖）。"""

    CHAT = "chat"        # 主 Agent：日常对话 / 行程规划
    FACT = "fact"        # 事实查询：票务 / 天气
    EXTRACT = "extract"  # 结构化提取
    TITLE = "title"      # 标题生成
    PLAN = "plan"        # 综合推荐生成


# 各任务默认「模型 + 温度」；主模型 DeepSeek-v4-pro，提取/规划用 qwen-max
TASK_DEFAULTS: dict[TaskKind, dict] = {
    TaskKind.CHAT:    {"model": VoyageModel.DEEPSEEK_V4_PRO,   "temperature": 0.7},
    TaskKind.FACT:    {"model": VoyageModel.DEEPSEEK_V4_FLASH, "temperature": 0.2},
    TaskKind.EXTRACT: {"model": VoyageModel.QWEN_MAX,          "temperature": 0.1},
    TaskKind.TITLE:   {"model": VoyageModel.DEEPSEEK_V4_FLASH, "temperature": 0.3},
    TaskKind.PLAN:    {"model": VoyageModel.QWEN_MAX,          "temperature": 0.6},
}


def get_task_llm(task: TaskKind, **overrides) -> BaseChatModel:
    """按任务类型获取 LLM：默认模型与温度见 TASK_DEFAULTS，可用关键字覆盖。"""
    return get_llm(**{**TASK_DEFAULTS[task], **overrides})


def get_llm(
    model: str | VoyageModel = VoyageModel.DEEPSEEK_V4_PRO,
    temperature: float = 1.0,
    api_key: str | None = None,
    base_url: str | None = None,
    model_provider: Literal["openai", "deepseek"] | None = None,
) -> BaseChatModel:
    """
    统一的 LLM 实例获取工厂函数
    
    能够根据传入的 model 动态推断适配的 API Key、Base URL 与 Provider。
    """
    # 1. 因为是 StrEnum，直接转为标准 str 类型即可（兼顾兼容外部传入的字符串）
    model_name = str(model)

    # 2. 动态推断 API Key 与 Base URL
    # if "deepseek" in model_name:
    #     base_url = base_url or config.DEEPSEEK_BASE_URL
    #     api_key = api_key or config.DEEPSEEK_API_KEY
    # else:
    #     base_url = base_url or config.DASHSCOPE_BASE_URL
    #     api_key = api_key or config.DASHSCOPE_API_KEY
    
    base_url = config.DASHSCOPE_BASE_URL
    api_key = config.DASHSCOPE_API_KEY

    # 3. 只有当外部没有指定 provider 时，才提供默认值 "openai"
    provider = model_provider or "openai"

    return init_chat_model(
        model=model_name,
        model_provider=provider,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        extra_body={
        "enable_thinking": False,           # Qwen3 / 很多国内兼容网关
        # "chat_template_kwargs": {"enable_thinking": False},  # vLLM / SGLang 常见
        # "thinking": {"type": "disabled"},  # 部分网关
        # "reasoning": {"enabled": False},   # 部分 DeepSeek 兼容
        # "reasoning_effort": "none",        # 支持 effort 的推理模型
    },
    )