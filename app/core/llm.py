from langchain.chat_models import init_chat_model
from app.config import config


def get_default_llm():
    return init_chat_model(
        "qwen3.5-flash",
        model_provider="openai",
        base_url=config.DASHSCOPE_BASE_URL,
        api_key=config.DASHSCOPE_API_KEY,
    )


def get_deepseek_llm():
    return init_chat_model(
        "deepseek-v4-flash",
        model_provider="openai",
        base_url=config.DEEPSEEK_BASE_URL,
        api_key=config.DEEPSEEK_API_KEY,
    )