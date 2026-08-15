# config/agents/travel.py
from langchain.agents import create_agent

from app.core.ai.config.mcp import get_namespace_tools
from app.core.ai.llm import get_llm

TRAVEL_AGENT_PROMPT = """你是一个目的地综合规划专家（Travel Agent）。
结合到站信息、天气与用户预算约束，进行推荐。

### 推荐规则：
1. **🏨 酒店**：严格不超过用户预算；优先推荐到达车站附近（步行/打车15分钟内）
2. **🎯 景点**：雨天推荐室内场馆/博物馆，晴天可推荐户外；控制景点间通勤距离
3. **🍜 美食**：推荐景点附近（2公里内）地道特色餐饮

### 输出格式（Markdown）：
```markdown
### 🏨 住宿建议
- ...

### 🎯 精选景点
- ...

### 🍜 周边美食
- ...
```
"""


# 已构建的 agent 惰性缓存（一个进程内只建一次，复用一个 MCP 连接）
_travel_agent_cache = None


async def get_travel_agent():
    """惰性获取 Travel 子 Agent：首次调用时异步构建并缓存。"""
    global _travel_agent_cache
    if _travel_agent_cache is None:
        tools = await get_namespace_tools("travel")
        _travel_agent_cache = create_agent(
            name="travel_agent",
            model=get_llm(),
            tools=tools,
            system_prompt=TRAVEL_AGENT_PROMPT,
        )
    return _travel_agent_cache
