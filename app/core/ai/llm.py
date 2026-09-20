"""LLM 工厂：按配置在 OpenCode Go / DeepSeek 官方 / SenseAudio / 智谱之间切换（均为 OpenAI 兼容）。

设计要点
--------
- 全平台所有任务共用同一模型，按任务只区分温度；具体模型由 config.LLM_CHANNEL
  决定的通道默认模型给出（也可调用方显式覆盖）；
- 请求头（x-opencode-session / User-Agent）由 opencode.py 在请求发出时注入，
  这里只负责把共享的 httpx 客户端交给 ChatOpenAI；
- 不传 extra_body 的 enable_thinking：那是 DashScope 专有参数，本通道会拒绝。
"""
from enum import StrEnum
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import config

from .opencode import build_http_client, build_sync_http_client
from .token import token_counter

# 全局共享的 httpx 客户端：复用连接池，并动态注入 OpenCode Go 必需的会话头。
# 同步客户端仅为满足 ChatOpenAI 的初始化校验（项目内不存在同步调用路径）。
_http_client = build_http_client()
_sync_http_client = build_sync_http_client()


def _resolve_channel() -> tuple[str, str, str]:
    """按 config.LLM_CHANNEL 解析当前通道的 (base_url, api_key, 默认模型)。

    - opencode：OpenCode Go 网关（默认）
    - deepseek：DeepSeek 官方 OpenAI 兼容端点
    - senseaudio：SenseAudio OpenAI 兼容网关（glm 系列模型）
    - zhipu：智谱 BigModel OpenAI 兼容网关（glm 系列模型）
    未知取值按 opencode 处理，避免因配置拼写错误导致启动即不可用。
    """
    channel = config.LLM_CHANNEL.strip().lower()
    if channel == "deepseek":
        return (
            config.DEEPSEEK_BASE_URL,
            config.DEEPSEEK_API_KEY,
            config.DEEPSEEK_LLM_MODEL_FLASH,
        )
    if channel == "senseaudio":
        return (
            config.SENSEAUDIO_BASE_URL,
            config.SENSEAUDIO_API_KEY,
            config.SENSEAUDIO_LLM_MODEL,
        )
    if channel == "zhipu":
        return (
            config.ZHIPU_BASE_URL,
            config.ZHIPU_API_KEY,
            config.ZHIPU_LLM_MODEL,
        )
    return config.OPENCODE_GO_URL, config.OPENCODE_API_KEY, config.OPENCODE_LLM_MODEL


def get_llm_channel_info() -> dict:
    """返回当前 LLM 通道信息，供管理端健康检查展示（不发起真实调用）。"""
    base_url, api_key, model = _resolve_channel()
    return {
        "channel": config.LLM_CHANNEL,
        "base_url": base_url,
        "model": model,
        "configured": bool(base_url and api_key),
    }


class VoyageModel(StrEnum):
    """Voyage 平台支持的模型（OpenCode Go 通道）。"""

    # 全任务统一模型：速度快、成本低、月度额度高
    DEEPSEEK_V4_1_FLASH = "deepseek-v4.1-flash"
    # 同系列备选（仅用于对比/压测，默认路由不使用）
    DEEPSEEK_V4_FLASH = "deepseek-v4-flash"
    DEEPSEEK_FLASH = "deepseek-flash"


class TaskKind(StrEnum):
    """LLM 任务类型：决定温度（调用处仍可覆盖）。"""

    CHAT = "chat"        # 主 Agent：日常对话 / 行程规划
    FACT = "fact"        # 事实查询：票务 / 天气
    EXTRACT = "extract"  # 结构化提取
    TITLE = "title"      # 标题生成
    PLAN = "plan"        # 综合推荐生成


# 各任务默认温度：模型统一，故只需按任务调温度。
# 抽取类要稳定（低温），创作类要发散（高温）。
TASK_TEMPERATURES: dict[TaskKind, float] = {
    TaskKind.CHAT: 0.7,
    TaskKind.FACT: 0.2,
    TaskKind.EXTRACT: 0.1,
    TaskKind.TITLE: 0.3,
    TaskKind.PLAN: 0.6,
}

# 需要关闭「思考模式」的任务。
#
# 原因：该通道的 deepseek-v4.1-flash 默认开启思考，而思考模式下强制指定
# tool_choice 会被上游拒绝（400 Thinking mode does not support this tool_choice）。
# 结构化提取依赖强制工具调用，故必须关闭思考；其余任务保留思考，
# 以便前端展示推理过程并提升复杂规划质量。
TASK_REASONING_OFF: frozenset[TaskKind] = frozenset({TaskKind.EXTRACT})


def get_task_llm(task: TaskKind, **overrides) -> BaseChatModel:
    """按任务类型获取 LLM：默认温度见 TASK_TEMPERATURES，可用关键字覆盖。"""
    params: dict = {"temperature": TASK_TEMPERATURES[task]}
    # 关闭思考的两种情况：任务本身必须关闭（EXTRACT），或全局开关打开；
    # overrides 最后合并，故调用方仍可显式传 reasoning_effort 覆盖。
    if task in TASK_REASONING_OFF or config.LLM_DISABLE_REASONING:
        params["reasoning_effort"] = "none"
    params.update(overrides)
    return get_llm(**params)


def get_llm(
    model: str | VoyageModel | None = None,
    temperature: float = 1.0,
    api_key: str | None = None,
    base_url: str | None = None,
    model_provider: Literal["openai"] | None = None,
    reasoning_effort: str | None = None,
) -> BaseChatModel:
    """统一的 LLM 实例获取工厂函数。

    Args:
        model: 模型 ID；不传时取当前通道（config.LLM_CHANNEL）的默认模型
        temperature: 采样温度
        api_key / base_url: 显式覆盖通道配置（默认按 LLM_CHANNEL 解析）
        model_provider: 仅支持 OpenAI 兼容协议（本通道的 /chat/completions）
        reasoning_effort: 传 "none" 关闭思考模式（强制工具调用场景需要）
    """
    channel_base_url, channel_api_key, channel_model = _resolve_channel()

    model_name = str(model) if model is not None else channel_model
    resolved_base_url = base_url or channel_base_url
    resolved_api_key = api_key or channel_api_key

    # 关闭思考模式的参数因网关而异：
    # - 智谱：用 thinking={"type":"disabled"}；其 glm-4.x/5-turbo 接受该参数，
    #   而 glm-5.x 系属「始终思考」，传了会 400，故换模型而非换参数。
    #   同时不能再下发 reasoning_effort，否则智谱会以参数冲突报错。
    # - 其它（DeepSeek/SenseAudio/OpenCode）：用 OpenAI 兼容的 reasoning_effort。
    extra_body = None
    if reasoning_effort == "none":
        if config.LLM_CHANNEL.strip().lower() == "zhipu":
            extra_body = {"thinking": {"type": "disabled"}}
            reasoning_effort = None
        else:
            extra_body = {"reasoning_effort": "none"}

    return init_chat_model(
        model=model_name,
        model_provider=model_provider or "openai",
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        extra_body=extra_body,
        callbacks=[token_counter],          # Token 用量统计回调
        http_async_client=_http_client,
        http_client=_sync_http_client,
        http_socket_options=(),             # 禁用自带传输层，交由自定义客户端控制
    )


async def close_http_client() -> None:
    """释放共享 httpx 客户端（FastAPI 关闭钩子中调用）。"""
    if not _http_client.is_closed:
        await _http_client.aclose()
    if not _sync_http_client.is_closed:
        _sync_http_client.close()
