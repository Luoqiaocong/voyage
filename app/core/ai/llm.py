from enum import StrEnum
from typing import Literal
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import config


class VoyageModel(StrEnum):
    """Voyage 平台支持的模型枚举"""
    DEEPSEEK_V4_FLASH = "deepseek-v4-flash"
    DEEPSEEK_V4_PRO = "deepseek-v4-pro"
    QWEN_3_5_FLASH = "qwen3.5-flash"
    QWEN_MAX = "qwen-max"
    DASHCOPE_GLM_5 = "glm-5"


def get_llm(
    model: str | VoyageModel = VoyageModel.QWEN_3_5_FLASH,
    temperature: float = 1.4,
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
    if "deepseek" in model_name:
        base_url = base_url or config.DEEPSEEK_BASE_URL
        api_key = api_key or config.DEEPSEEK_API_KEY
    else:
        base_url = base_url or config.DASHSCOPE_BASE_URL
        api_key = api_key or config.DASHSCOPE_API_KEY

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