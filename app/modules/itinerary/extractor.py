"""行程专属结构化提取：把对话攻略 Markdown → ItineraryPlan。

依赖方向：modules → core（行程域提供 schema 与专属提示词，调用 core 的通用提取器）。
"""
from app.core.ai.structured import extract_structured

from .schemas import ItineraryPlan

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


async def extract_itinerary_plan(recommend_txt: str):
    """攻略 Markdown → ItineraryPlan；失败返回 None（不打断对话）。"""
    return await extract_structured(
        recommend_txt,
        ItineraryPlan,
        system_instructions=_EXTRACT_SYSTEM_PROMPT,
    )