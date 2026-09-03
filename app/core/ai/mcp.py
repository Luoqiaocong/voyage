import asyncio
import os

from langchain.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.shared.utils import log

# ===================== 1. MCP 配置字典 =====================
MCPCONFIG = {
    "TICKET_TOOLS_CONFIG": {
        "12306-mcp": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/61b1655c916844/mcp",
        },
    },
    "WEATHER_TOOLS_CONFIG": {
        "Weather-service": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/aa891a32a54645/mcp",
        },
    },
    "TRAVEL_TOOLS_CONFIG": {
        "duckduckgo-mcp-server": {
            "transport": "stdio",
            "command": "cmd",
            "args": ["/c", "uvx", "duckduckgo-mcp-server"],
            "env": {**os.environ},
        },
        "AI_Go_Hotel_MCP": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/77461314a7b246/mcp",
        },
        "hotel-recommend": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/435a851e7af345/mcp",
        },
        "travel_food": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/cca0e88b098e43/mcp",
        },
    },
}

# ===================== 2. 命名空间映射 =====================
NAMESPACE_MEMO = {
    "ticket": "TICKET_TOOLS_CONFIG",
    "weather": "WEATHER_TOOLS_CONFIG",
    "travel": "TRAVEL_TOOLS_CONFIG",
}

# ===================== 3. Client 缓存与工具获取 =====================
# 缓存已初始化的 Client 实例，避免重复建连和资源泄漏
_clients_cache: dict[str, MultiServerMCPClient] = {}


TOOL_FETCH_TIMEOUT_SECONDS = 10.0


async def get_namespace_tools(namespace: str) -> list[BaseTool]:
    """
    根据命名空间获取对应的 MCP 工具列表（带超时与降级）。
    自动缓存 MultiServerMCPClient 实例以复用连接；拉取失败返回空列表，
    由子 Agent 提示词的兜底话术接管应答，不让单个 MCP 端点卡死整个请求。
    """
    # 1. 查映射表
    config_key = NAMESPACE_MEMO.get(namespace)
    if not config_key:
        valid_keys = ", ".join(NAMESPACE_MEMO.keys())
        raise ValueError(f"未知的 namespace '{namespace}'，有效值为: {valid_keys}")

    # 2. 取出对应的配置字典
    tools_config = MCPCONFIG.get(config_key, {})
    if not tools_config:
        return []

    # 3. 复用或创建 Client 实例，整体限时拉取工具
    try:
        if namespace not in _clients_cache:
            _clients_cache[namespace] = MultiServerMCPClient(tools_config)

        tools = await asyncio.wait_for(
            _clients_cache[namespace].get_tools(),
            timeout=TOOL_FETCH_TIMEOUT_SECONDS,
        )
        log.info(f"[mcp] namespace '{namespace}' 工具就绪：{len(tools)} 个")
        return tools
    except Exception as exc:  # noqa: BLE001 - 统一降级入口，避免单个 MCP 端点拖垮请求
        # 降级：丢弃失败缓存，返回空工具列表（子 Agent 兜底话术接管）
        _clients_cache.pop(namespace, None)
        log.error(f"[mcp] namespace '{namespace}' 不可用：{exc}")
        return []
