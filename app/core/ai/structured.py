"""AI 结构化输出：把对话中的攻略 Markdown 整理为 ItineraryPlan JSON。"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.ai.llm import get_llm
from app.modules.itineraries.schemas import ItineraryPlan

# 关键：把完整输出结构写死在提示词里，防止模型不遵守 tool schema 绑定而自由发挥字段名
_EXTRACT_SYSTEM_PROMPT = """把用户提供的旅行攻略（Markdown）转换为 JSON，字段必须严格按下面的结构输出，禁止新增、改名或删除任何字段：

{
  "destination": "目的地，如 杭州",
  "days": 3,
  "budget": 3000,
  "preferences": ["美食", "亲子"],
  "transport": "往返交通建议",
  "accommodation": {
    "time_slot": "evening",
    "kind": "hotel",
    "name": "酒店名",
    "description": "一句话说明",
    "duration_hours": 12,
    "cost": 400,
    "note": "预订提示等"
  },
  "daily_plans": [
    {
      "day_no": 1,
      "date": "2026-08-15",
      "theme": "当天主题",
      "summary": "一句话总结",
      "activities": [
        {
          "time_slot": "morning",
          "kind": "attraction",
          "name": "西湖",
          "description": "一句话亮点",
          "duration_hours": 3,
          "cost": 0,
          "note": "提示"
        }
      ]
    }
  ],
  "tips": ["提醒句子一", "提醒句子二"]
}

约束（必须遵守）：
1. 只整理攻略中已有的信息，不要编造或补全；攻略里没有的字段就省略该字段
2. time_slot 只能是 morning / afternoon / evening 之一
3. kind 只能是 attraction / restaurant / hotel / transport / rest 之一
4. daily_plans 按第 1 天到第 N 天排列，长度必须等于 days
5. tips 是字符串数组，每条是一句完整提醒，禁止用对象或分类
6. 只输出 JSON，不要输出任何其他文字或 Markdown 代码块
"""


async def extract_itinerary_plan(markdown: str) -> ItineraryPlan | None:
    """攻略 Markdown → ItineraryPlan；失败返回 None（不打断对话）。"""
    if not markdown or not markdown.strip():
        return None
    try:
        structured_llm = get_llm(temperature=0.2).with_structured_output(ItineraryPlan)
        plan = await structured_llm.ainvoke([
            SystemMessage(content=_EXTRACT_SYSTEM_PROMPT),
            HumanMessage(content=markdown),
        ])
        return plan
    except Exception as exc:
        # 开发期排查用：打印完整校验信息（含模型原始输出片段）
        print(f"[extract_itinerary_plan] failed: {exc}")  # noqa: T201
        return None