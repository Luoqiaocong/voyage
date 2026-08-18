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

    CHUNK_SIZE: int = 1024
    CHUNK_OVERLAP: int = 200
    TOP_K: int = 10
    RERANK_TOP_N: int = 5
    
    JWT_SECRET_KEY:str
    JWT_ALGORITHM:str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES:int
    JWT_REFRESH_TOKEN_EXPIRE_DAYS:int
    HASH_SALT:str


    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False
    )


config = VoyageConfig()   # type: ignore

if __name__ == "__main__":
    print(config.model_dump_json(indent=2))