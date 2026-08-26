"""行程专属结构化提取：把对话攻略 Markdown → ItineraryPlan。

依赖方向：modules → core（行程域提供 schema 与专属提示词，调用 core 的通用提取器）。
"""
from app.core.ai.tasks import extract_structured

from .schemas import ItineraryPlan

# 关键：把完整输出结构写死在提示词里，防止模型不遵守 tool schema 绑定而自由发挥字段名
_EXTRACT_SYSTEM_PROMPT = """你是一个旅行攻略结构化提取器。请根据用户提供的 Markdown 攻略，提取关键信息并按 JSON 格式输出。

【输出结构】
{
  "destination": "目的地名称",
  "days": 行程总天数（整数，与 daily_plans 数量一致）,
  "budget": 预算（整数）,
  "preferences": ["偏好1", "偏好2"],
  "transport": "交通建议",
  "accommodation": {
    "time_slot": "morning 或 afternoon 或 evening",
    "kind": "hotel",
    "name": "住宿名称",
    "description": "一句话描述",
    "duration_hours": 12,
    "cost": 400,
    "note": "预订提示"
  },
  "daily_plans": [
    {
      "day_no": 1,
      "date": "日期（可选）",
      "theme": "当天主题",
      "summary": "一句话总结",
      "activities": [
        {
          "time_slot": "morning 或 afternoon 或 evening",
          "kind": "attraction",
          "name": "景点或场所名称",
          "description": "一句话描述",
          "duration_hours": 3,
          "cost": 0,
          "note": "提示（可选）"
        }
      ]
    }
  ],
  "tips": ["提醒1", "提醒2"]
}

【字段要求】
1. 只提取攻略中明确提到的信息，不要编造或补全；攻略里没有的字段直接省略（不要填 null 或空字符串）
2. accommodation 是一个 JSON 对象，必须用大括号 {} 输出，绝不能写成字符串；攻略没有明确住宿建议时，省略整个 accommodation 字段
3. 所有嵌套结构（accommodation、daily_plans 中的每个活动）都必须以真正的 JSON 对象/数组形式存在，禁止用字符串包裹
4. time_slot 只能是三个英文值之一：morning / afternoon / evening
5. kind 只能是五个英文值之一：attraction（景点/观光/购物）、restaurant（餐厅/美食）、hotel（住宿）、transport（交通）、rest（休息/自由活动）
6. 每个活动必须包含 name 字段，给一个真实合理的场所名称
7. daily_plans 的数量等于攻略中实际提到的天数，day_no 从 1 开始连续编号
8. tips 是字符串数组，每条是一句完整提醒
9. 只输出纯 JSON，不要 Markdown 代码块，不要任何多余文字

"""


async def extract_itinerary_plan(recommend_txt: str) -> ItineraryPlan | None:
    """攻略 Markdown → ItineraryPlan；失败返回 None（不打断对话）。"""
    return await extract_structured(
        recommend_txt,
        ItineraryPlan,
        system_instructions=_EXTRACT_SYSTEM_PROMPT,
    )