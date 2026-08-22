from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class VoyageConfig(BaseSettings):
    # ---------- AI 服务商配置（密钥类必须由 .env / 环境变量提供，不设默认值）----------
    DASHSCOPE_API_KEY: str
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    ALIYUN_BASE_URL: str = "https://ws-llq8baw8q88n1gjz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    TAVILY_API_KEY: str

    # ---------- 模型配置 ----------
    MULTIMODAL_EMBEDDING_MODEL: str = "tongyi-embedding-vision-plus"
    TEXT_EMBEDDING_MODEL: str = "text-embedding-v1"
    ALIYUN_LLM_MODEL: str = "qwen3-max"
    DEEPSEEK_LLM_MODEL_FLASH: str = "deepseek-v4-flash"
    DEEPSEEK_LLM_MODEL_PRO: str = "deepseek-v4-pro"
    RERANK_MODEL: str = "qwen3-rerank"

    # ---------- RAG 参数 ----------
    CHUNK_SIZE: int = 1024
    CHUNK_OVERLAP: int = 200
    TOP_K: int = 10
    RERANK_TOP_N: int = 5

    # ---------- JWT / 安全（密钥类必须由 .env / 环境变量提供，不设默认值）----------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 3000000
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    HASH_SALT: str

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False
    )


config = VoyageConfig()  # type: ignore

if __name__ == "__main__":
    print(config.model_dump_json(indent=2))