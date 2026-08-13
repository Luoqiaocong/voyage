from enum import Enum
from typing import Literal, Optional
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import config


class VoyageModel(str, Enum):
    """Voyage 平台支持的模型枚举"""
    DEEPSEEK_V4_FLASH = "deepseek-v4-flash"
    DEEPSEEK_V4_PRO = "deepseek-v4-pro"
    QWEN_3_5_FLASH = "qwen3.5-flash"
    QWEN_MAX = "qwen-max"
    DASHCOPE_GLM_5 = "glm-5"


def get_llm(
    model: str | VoyageModel = VoyageModel.QWEN_3_5_FLASH,
    temperature: float = 0.2,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model_provider: Literal["openai", "deepseek"] = "openai",
) -> BaseChatModel:
    """
    统一的 LLM 实例获取工厂函数
    
    能够根据传入的 model 动态推断适配的 API Key 与 Base URL，避免参数错配。
    """
    # 1. 确保 model 拿到的是字符串值
    model_name = getattr(model, "value", model)

    if "deepseek" in model_name:
        base_url = base_url or config.DEEPSEEK_BASE_URL
        api_key = api_key or config.DEEPSEEK_API_KEY
        model_provider = "openai"
    else:
        base_url = base_url or config.DASHSCOPE_BASE_URL
        api_key = api_key or config.DASHSCOPE_API_KEY
        model_provider = "openai"

    return init_chat_model(
        model=model_name,
        model_provider=model_provider,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )