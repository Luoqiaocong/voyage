import os
from langchain.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

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


async def get_namespace_tools(namespace: str) -> list[BaseTool]:
    """
    根据命名空间获取对应的 MCP 工具列表。
    自动缓存 MultiServerMCPClient 实例以复用连接。
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

    # 3. 复用或创建 Client 实例
    if namespace not in _clients_cache:
        client = MultiServerMCPClient(tools_config)
        # 注意：如果 SDK 要求显式初始化/connect，需在此处 await
        _clients_cache[namespace] = client

    # 4. 获取工具
    tools = await _clients_cache[namespace].get_tools()
    return tools
