from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class VoyageConfig(BaseSettings):
    # ---------- LLM 通道选择 ----------
    # 可选 "opencode"（默认，OpenCode Go）/ "deepseek"（DeepSeek 官方，OpenAI 兼容）。
    # 该开关同时决定 get_llm() 使用的 base_url、api_key 与默认模型，
    # 使同一套业务代码可以在两个网关之间切换，无需改动调用方。
    LLM_CHANNEL: str = "opencode"

    # ---------- 思考模式开关 ----------
    # True = 所有任务关闭思考（reasoning_effort="none"）。
    # 关闭后模型不再产出 reasoning_content，首字延迟更低、也省 reasoning token；
    # 关闭思考是**全局强制**的，仍可被调用方显式传入的 reasoning_effort 覆盖。
    # 说明：EXTRACT（结构化提取）因强制 tool_choice 必须关闭思考，不受此开关影响。
    LLM_DISABLE_REASONING: bool = False

    # ---------- 模型配置 ----------
    # 全任务统一使用该模型（OpenCode Go 通道）：速度快、成本低、月度额度高
    OPENCODE_LLM_MODEL: str = "deepseek-v4.1-flash"

    # ---------- OpenCode Go（唯一 LLM 通道，OpenAI 兼容）----------
    # 注意：该网关强制要求每个请求携带 x-opencode-session 头，
    # 缺失会直接返回 400 MissingSessionID；CLIENT_USER_AGENT 用于自报客户端身份，
    # 避免被网关按通用 SDK 流量限流。
    #
    # 这里**没有多通道配置**：早先曾保留 DashScope / DeepSeek 官方 / 阿里云
    # 三组参数，但代码从未读取过它们（全项目零引用），其中两个还被声明为
    # 必填项 —— 结果是「不填这些用不到的密钥就无法启动」。
    # 已全部移除。若要恢复多通道或降级能力，需连同调用层一起实现，
    # 只加配置项没有意义。
    OPENCODE_GO_URL: str
    OPENCODE_API_KEY: str
    OPENCODE_DEFAULT_SESSION: str = "voyage-anonymous"
    CLIENT_USER_AGENT: str = "voyage-travel-assistant/1.0"
    APP_TIMEZONE: str = "Asia/Shanghai"

    # ---------- DeepSeek 官方通道（通过 LLM_CHANNEL=deepseek 启用）----------
    # 启用后 get_llm() 会读取这里的 base_url / api_key，并把默认模型切到
    # DEEPSEEK_LLM_MODEL_FLASH。未启用时这些配置不参与调用。
    # 为什么默认给空串而不是像原先那样声明为必填：
    # 必填项不填就无法启动，而默认通道并不使用它们 —— 等于用一把
    # 用不到的钥匙把门锁上。给空默认值后，未配置也能正常启动。
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    # 官方通道的模型名。注意与 OpenCode 通道的 deepseek-v4.1-flash 不是同一个
    # 模型，工具调用能力未必等价，切换前需要单独验证。
    DEEPSEEK_LLM_MODEL_FLASH: str = "deepseek-flash"
    DEEPSEEK_LLM_MODEL_PRO: str = "deepseek-v4-pro"

    # ---------- SenseAudio 通道（通过 LLM_CHANNEL=senseaudio 启用）----------
    # OpenAI 兼容网关，模型 id 形如 glm-5.3-flash（注意官方 id 带连字符）。
    # 与 DeepSeek 通道同理：未启用时这些配置不参与调用，故默认给空值。
    SENSEAUDIO_API_KEY: str = ""
    SENSEAUDIO_BASE_URL: str = "https://api.senseaudio.cn/v1"
    SENSEAUDIO_LLM_MODEL: str = "glm-5.3-flash"

    # ---------- 智谱 BigModel 通道（通过 LLM_CHANNEL=zhipu 启用）----------
    # OpenAI 兼容网关；默认选 GLM-4.5-Air：0.8/2 元每百万 token，可关闭思考
    # （thinking={"type":"disabled"}），实测多工具调用稳定、首字延迟低。
    # 注意：glm-5.x 系为「始终思考」，不接受关闭思考，不要用作本通道模型。
    ZHIPU_API_KEY: str = ""
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_LLM_MODEL: str = "glm-4.5-air"

    # ---------- 管理端：模型单价（每百万 token，美元）----------
    # 用于看板成本估算。默认值取 OpenCode Go 的 DeepSeek V4.1 Flash 非高峰价；
    # 高峰时段（UTC 周一至周五 01:00-04:00 与 06:00-10:00）单价翻倍，
    # 故估算值偏保守（偏低）。未配置单价的模型按 0 计并在结果中标注。
    MODEL_PRICING: dict[str, dict[str, float]] = {
        "deepseek-v4.1-flash": {"input": 0.15, "output": 0.60},
    }

    # 以人民币报价的模型单价（每百万 token），来源为 SenseAudio 官方报价。
    # 看板统一以美元展示，读取时按 CNY_PER_USD 折算，避免把两种币种直接相加。
    MODEL_PRICING_CNY: dict[str, dict[str, float]] = {
        "glm-5.3-flash": {"input": 0.8, "output": 2.8},
        # 智谱 GLM-4.5-Air（主模型）与廉价备选 GLM-4-FlashX。
        "glm-4.5-air": {"input": 0.8, "output": 2.0},
        "glm-4-flashx": {"input": 0.1, "output": 0.1},
    }
    # 人民币兑美元汇率：仅用于把 MODEL_PRICING_CNY 折算成看板使用的美元。
    # 汇率会波动，按需调整；填 0 会被当作 1 处理以免除零。
    CNY_PER_USD: float = 7.2

    # ---------- 管理端：用量落库与看板 ----------
    USAGE_FLUSH_INTERVAL_SECONDS: int = 60   # 后台把 Redis 增量落库的周期（秒）
    USAGE_DAYS_TREND_DEFAULT: int = 7        # 趋势图默认天数
    USAGE_DAYS_TREND_MAX: int = 90           # 趋势图允许的最大天数（防滥用）
    ADMIN_PAGE_SIZE_DEFAULT: int = 20        # 管理端分页默认每页条数
    ADMIN_PAGE_SIZE_MAX: int = 100           # 管理端分页每页上限

    # ---------- 行程分享 ----------
    # 生成完整分享链接时使用的对外基址（前端域名）。
    # 分享接口返回的 url 由它 + /share/{token} 拼成，便于前端直接复制。
    # 部署到服务器时务必改成实际可访问的地址，否则分享出去的链接点不开。
    SHARE_BASE_URL: str = "http://localhost:5173"

    # ---------- 跨域 ----------
    # 留空 = 允许所有来源（开发便利）。生产环境应显式列出前端域名。
    # 同源部署（nginx 把 /api 反代到后端）时无需配置此项。
    ALLOWED_ORIGINS: list[str] = []

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
    
    # ---------- Redis ----------
    # 连接**只由 REDIS_URL 决定**（见 shared/redis/client.py 的 from_url）。
    #
    # 下面三项是早先按 host/port/db 分项配置时留下的，代码从未读取它们
    # （client.py 里对应的三行是注释掉的旧实现）。其中 REDIS_HOST 还被声明为
    # 必填 —— 又是一处「不填一把用不到的钥匙就无法启动」。
    #
    # 保留这三项是为了兼容既有 .env / docker-compose（那边仍在注入它们），
    # 但全部给默认值、不再必填。它们**不影响实际连接**：
    # 想换 Redis 实例请改 REDIS_URL。
    REDIS_URL: str
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 7

    # ---------- 数据库 ----------
    # 主用 PostgreSQL：postgresql+asyncpg://user:pwd@host:5432/dbname
    # 留空则回退到 SQLite（data/exports/app.db），便于本地开发与单元测试。
    # 部署时建议用环境变量注入，而不是写进 .env 文件。
    DATABASE_URL: str = ""
    # langgraph checkpointer 用的连接串（psycopg 驱动，非 asyncpg）。
    # 留空则由 DATABASE_URL 推导；两者驱动不同，故允许单独覆盖。
    CHECKPOINT_DATABASE_URL: str = ""
    

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        # 忽略 .env / 环境变量里未声明的键。
        #
        # 必须显式设置：pydantic-settings v2 对 BaseSettings 的默认值是
        # **extra="forbid"**，也就是说 .env 里多出一个键就会抛
        # ValidationError 让整个应用起不来 —— 实测确认过。
        #
        # 为什么这是错的默认行为（对我们而言）：
        #   · 部署机上往往沿用旧版 .env，删掉/重命名配置项后旧键仍在，
        #     结果服务直接无法启动，而报错发生在配置加载阶段，
        #     排查成本高、表现还像「代码坏了」
        #   · 环境变量是共享空间，别的工具注入的变量也会被算作「多余输入」
        # 配置项改名或下线时，旧 .env 应当继续可用（多余键被忽略），
        # 而不是把服务锁死。
        extra="ignore",
    )


config = VoyageConfig()  # type: ignore

if __name__ == "__main__":
    print(config.model_dump_json(indent=2))