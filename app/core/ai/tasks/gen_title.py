"""会话标题生成：根据首轮对话内容概括主题（失败不影响主流程）。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain.messages import HumanMessage

from app.core.ai.llm import TaskKind, get_task_llm


async def generate_conversation_title(conversation_text: str) -> str:
    """根据对话内容生成简短标题（5-10 个字）。

    Args:
        conversation_text: 对话文本（用户消息 + AI 回复）

    Returns:
        标题字符串，如「北京三日游行程规划」；结果异常时给出兜底标题。
    """

    prompt = f"""
你是一个对话标题生成助手。请根据以下对话内容，生成一个简短精炼的标题（5-10个字）。

要求：
1. 概括对话的核心主题
2. 如果是旅行规划，格式为「目的地 + 天数 + 行程/攻略」
3. 如果是美食推荐，格式为「目的地 + 美食探索」
4. 不要用「关于」「讨论」等虚词开头
5. 直接输出标题，不要任何解释
6. 主要以用户消息的概要为核心

对话内容：
{conversation_text}

"""

    response = await get_task_llm(TaskKind.TITLE).ainvoke([HumanMessage(content=prompt)])
    title = response.content.strip() if isinstance(response.content, str) else ""

    # 兜底：AI 返回空或过长时给默认标题（展示用本地时间）
    if not title or len(title) > 30:
        local_date = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
        title = f"新对话-{local_date}"

    return title