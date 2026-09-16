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
    # 全任务统一使用该模型（OpenCode Go 通道）：速度快、成本低、月度额度高
    OPENCODE_LLM_MODEL: str = "deepseek-v4.1-flash"

    # ---------- OpenCode Go（当前唯一可用的 LLM 通道，OpenAI 兼容）----------
    # 注意：该网关强制要求每个请求携带 x-opencode-session 头，
    # 缺失会直接返回 400 MissingSessionID；CLIENT_USER_AGENT 用于自报客户端身份，
    # 避免被网关按通用 SDK 流量限流。
    OPENCODE_GO_URL: str
    OPENCODE_API_KEY: str
    OPENCODE_DEFAULT_SESSION: str = "voyage-anonymous"
    CLIENT_USER_AGENT: str = "voyage-travel-assistant/1.0"
    APP_TIMEZONE: str = "Asia/Shanghai"

    # ---------- 历史通道（DashScope 免费额度已耗尽，保留仅供回退/对比）----------
    ALIYUN_LLM_MODEL: str = "qwen3-max"
    DEEPSEEK_LLM_MODEL_FLASH: str = "deepseek-v4-flash"
    DEEPSEEK_LLM_MODEL_PRO: str = "deepseek-v4-pro"

    # ---------- 管理端：模型单价（每百万 token，美元）----------
    # 用于看板成本估算。默认值取 OpenCode Go 的 DeepSeek V4.1 Flash 非高峰价；
    # 高峰时段（UTC 周一至周五 01:00-04:00 与 06:00-10:00）单价翻倍，
    # 故估算值偏保守（偏低）。未配置单价的模型按 0 计并在结果中标注。
    MODEL_PRICING: dict[str, dict[str, float]] = {
        "deepseek-v4.1-flash": {"input": 0.15, "output": 0.60},
    }

    # ---------- 管理端：用量落库与看板 ----------
    USAGE_FLUSH_INTERVAL_SECONDS: int = 60   # 后台把 Redis 增量落库的周期（秒）
    USAGE_DAYS_TREND_DEFAULT: int = 7        # 趋势图默认天数
    USAGE_DAYS_TREND_MAX: int = 90           # 趋势图允许的最大天数（防滥用）
    ADMIN_PAGE_SIZE_DEFAULT: int = 20        # 管理端分页默认每页条数
    ADMIN_PAGE_SIZE_MAX: int = 100           # 管理端分页每页上限

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
    
    REDIS_URL:str
    REDIS_HOST:str
    REDIS_PORT:int=6379
    REDIS_DB:int=7
    

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False
    )


config = VoyageConfig()  # type: ignore

if __name__ == "__main__":
    print(config.model_dump_json(indent=2))