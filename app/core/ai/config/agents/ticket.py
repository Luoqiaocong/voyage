# config/agents/ticket.py
from langchain.agents import create_agent

from app.core.ai.config.mcp import get_namespace_tools
from app.core.ai.llm import get_llm

TICKET_AGENT_PROMPT = """你是一个交通票务查询专家（Ticket Agent）。
精准过滤出发时间段与坐席偏好，按价格或历时排序，列出前 3-5 趟车次。

### 输出格式（Markdown 表格）：
| 车次 | 出发站→到达站 | 出发时间→到达时间 | 历时 | 余票/票价 |
|------|-------------|-----------------|------|----------|
| GXXXX | 广州南→成都东 | 13:15→20:30 | 7h15m | 二等座 ¥520 余23张 |

### 规则：
- 若查询无结果，返回"当前无符合条件的车次"并说明原因。
- 末尾明确推荐最优车次及到站时间/站点。
"""


# 已构建的 agent 惰性缓存（一个进程内只建一次，复用一个 MCP 连接）
_ticket_agent_cache = None


async def get_ticket_agent():
    """惰性获取 Ticket 子 Agent：首次调用时异步构建并缓存。"""
    global _ticket_agent_cache
    if _ticket_agent_cache is None:
        tools = await get_namespace_tools("ticket")
        _ticket_agent_cache = create_agent(
            name="ticket_agent",
            model=get_llm(),
            tools=tools,
            system_prompt=TICKET_AGENT_PROMPT,
        )
    return _ticket_agent_cache
