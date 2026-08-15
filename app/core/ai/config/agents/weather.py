# config/agents/weather.py
from langchain.agents import create_agent

from app.core.ai.config.mcp import get_namespace_tools
from app.core.ai.llm import get_llm

WEATHER_AGENT_PROMPT = """你是一个气象与出行环境分析专家（Weather Agent）。
查询目的地指定日期范围的天气，给出出行建议。

### 输出内容：
1. 每日天气概览（气温、晴雨、风力）
2. 穿衣与携带物品建议（是否需要雨具/防晒/外套）
3. 户外活动适宜度评估

### 格式：
用 Markdown 列表或短段落输出，简洁清晰。
"""


# 已构建的 agent 惰性缓存（一个进程内只建一次，复用一个 MCP 连接）
_weather_agent_cache = None


async def get_weather_agent():
    """惰性获取 Weather 子 Agent：首次调用时异步构建并缓存。"""
    global _weather_agent_cache
    if _weather_agent_cache is None:
        tools = await get_namespace_tools("weather")
        _weather_agent_cache = create_agent(
            name="weather_agent",
            model=get_llm(),
            tools=tools,
            system_prompt=WEATHER_AGENT_PROMPT,
        )
    return _weather_agent_cache
