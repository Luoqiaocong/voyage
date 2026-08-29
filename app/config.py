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

    # ---------- 模型配置 ----------
    ALIYUN_LLM_MODEL: str = "qwen3-max"
    DEEPSEEK_LLM_MODEL_FLASH: str = "deepseek-v4-flash"
    DEEPSEEK_LLM_MODEL_PRO: str = "deepseek-v4-pro"

    # ---------- JWT / 安全（密钥类必须由 .env / 环境变量提供，不设默认值）----------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    HASH_SALT: str
    
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = False  # 是否输出到文件
    LOG_SAVE_PATH: str = "logs"  # 日志存放文件夹名
    
    RESEND_API_KEY: str
    MAIL_FROM_NAME:str  = "Voyage" 
    MAIL_FROM_ADDRESS:str = "noreply@v.hiseven.cn"

    # ---------- 邮件 SMTP（默认 Resend；切换供应商时只需改这几项）----------
    SMTP_HOST: str = "smtp.resend.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "resend"
    

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False
    )


config = VoyageConfig()  # type: ignore

if __name__ == "__main__":
    print(config.model_dump_json(indent=2))