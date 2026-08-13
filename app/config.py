from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class VoyageConfig(BaseSettings):
    DASHSCOPE_API_KEY: str
    DASHSCOPE_BASE_URL: str
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str
    ALIYUN_BASE_URL: str
    TAVILY_API_KEY: str

    MULTIMODAL_EMBEDDING_MODEL: str
    TEXT_EMBEDDING_MODEL: str
    ALIYUN_LLM_MODEL: str
    DEEPSEEK_LLM_MODEL_FLASH: str
    DEEPSEEK_LLM_MODEL_PRO: str
    RERANK_MODEL: str

    MILVUS_ALIYUN_URI: str
    MILVUS_COLLECTION_NAME: str
    MILVUS_DIM: int = 1156
    MILVUS_ALIYUN_ACCOUNT: str
    MILVUS_ALIYUN_PASSWORD: str

    CHUNK_SIZE: int = 1024
    CHUNK_OVERLAP: int = 200
    TOP_K: int = 10
    RERANK_TOP_N: int = 5

    POSTGRESQL_DATABASE_URL: str
    
    REDIS_URL: str = "redis://localhost:6379/2"  # 新增，带默认值
    MEMORY_MODE: str = "sliding"                 # sliding | summary | semantic
    MEMORY_WINDOW_SIZE: int = 10                 # 窗口大小
    MEMORY_TTL: int = 7200                       # 2小时
    MEMORY_SUMMARY_MODEL: str = "qwen3.5-flash"  # 摘要用轻量模型

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False
    )


config = VoyageConfig()   # type: ignore

if __name__ == "__main__":
    print(config.model_dump_json(indent=2))